# ADR-0003 — Cifrado en reposo de las credenciales de proveedores y rotación de la clave maestra

- **Estado:** Propuesto (se acepta junto con *Approved* de SPEC-04, con OK del dueño)
- **Fecha:** 2026-11-27
- **Specs afectadas:** SPEC-04 (dueña: RN-INT-04/05/06, RNF-INT-01/02, RF-INT-08/15, AC-INT-07/08/09/16/44), SPEC-03
  (`IntegrationContext`, RN-ENG-08), SPEC-05/06/07 (consumen credenciales resueltas), SPEC-10 (auditoría).
  Constitución `C-06`, `C-08`, `C-13`, `C-16`. Decisiones: Q-010, Q-014, Q-401, Q-405, Q-415, Q-418.

## Contexto
- `C-06` exige credenciales cifradas en reposo, nunca en logs, errores, respuestas ni fixtures, y rotación atómica.
  Una credencial filtrada expone la cuenta de cobro de un comercio (brief §8). El legacy tenía un único token en
  `.env` (`context/04-legacy-guazunchito.md`).
- Qué se guarda: por integración, un juego de credenciales cuyos campos y marca secreto/no secreto declara el
  adaptador (Q-401, SPEC-03 RF-ENG-06). En MP, un access token y un secreto de webhooks (SPEC-05 §9). Se cargan a
  mano (Q-014): no hay OAuth ni refresh en el MVP, así que no hay que guardar refresh tokens todavía.
- Lo secreto no vuelve a mostrarse nunca, ni parcial (Q-405); se descifra solo en memoria, para una operación de la
  misma organización (RN-INT-05).
- **Q-418 a)** (decidida el 2026-11-27): la clave maestra se rota **sin downtime**; las credenciales guardadas se
  re-cifran y las cifradas con claves anteriores siguen legibles hasta que el re-cifrado termina.
- El Hub es multi-tenant con esquema compartido (ADR-0001): una fila de credenciales de la organización B no tiene
  que poder servir para la organización A aunque alguien con escritura en la base la copie de una fila a otra.
- Restricciones: no hay hosting definido (Q-020, Q-065), así que no hay KMS de un proveedor de nube disponible hoy;
  opera una sola persona; volumen bajo (decenas de integraciones); toda dependencia nueva en zona roja necesita ADR y
  versión fijada (`C-13`). `cryptography==50.0.2` **ya está** fijada en `backend/pyproject.toml` (la usa el JWT
  ES256 de ADR-0004).

## Opciones
1. **AES-256-GCM (AEAD) de `cryptography`, con datos asociados (AAD) que atan el texto cifrado a su organización y
   su integración, y un llavero de claves con identificador** (elegida).
   - Pros: sin dependencia nueva; algoritmo estándar (NIST SP 800-38D) con autenticación integrada; el AAD hace que
     un texto cifrado copiado a otra fila u otra organización no se pueda descifrar; clave de 256 bits; el
     identificador de clave por fila permite leer con claves viejas mientras se rota.
   - Contras: un formato de sobre propio (versión, clave, nonce) que hay que escribir y revisar; nonce aleatorio de
     96 bits, seguro solo mientras cada clave cifre muy por debajo de 2³² mensajes (acá son cientos).
2. **Fernet / `MultiFernet` de `cryptography`.**
   - Pros: sin dependencia nueva; formato estándar con versión y fecha; `MultiFernet.rotate()` resuelve la lectura
     con varias claves; muy difícil de usar mal.
   - Contras: AES-128-CBC + HMAC-SHA256, **sin datos asociados**: atar el texto a su organización obliga a meter
     los IDs dentro del texto plano y verificarlos a mano después de descifrar; no lleva identificador de clave
     (prueba cada clave hasta que una valida), así que no se puede contar cuántas filas usan cada clave sin
     descifrarlas todas. Es la alternativa razonable si el sobre propio resultara difícil de revisar.
3. **Librería de campos cifrados de Django** (`django-fernet-fields`, `django-encrypted-model-fields` y similares).
   - Contras: dependencia nueva en zona roja (`C-13`) y varias sin mantenimiento; cifrado transparente en el campo,
     así que el valor en claro aparece en la instancia del modelo y puede salir por un serializer, un `repr`, el
     admin o una traza; sin AAD ni rotación sin downtime.
4. **`pgcrypto` en PostgreSQL.**
   - Contras: la clave viaja en cada consulta SQL y puede quedar en logs de la base (`log_statement`,
     `pg_stat_statements`) o en la traza de un error; la clave y los datos terminan en el mismo lugar.
5. **KMS de nube o HashiCorp Vault (cifrado de sobre con clave de datos envuelta).**
   - Pros: la clave maestra nunca sale del servicio; auditoría y rotación del propio servicio.
   - Contras: no hay hosting definido (Q-020, Q-065); Vault agrega un servicio que operar para una sola persona; las
     dos son dependencias y llamadas de red nuevas en cada resolución. **Diferida:** el formato elegido deja la
     puerta abierta (ver Consecuencias).
6. **Derivar la clave de `DJANGO_SECRET_KEY`.**
   - Contras: acopla dos rotaciones (rotar el secreto de Django volvería ilegibles todas las credenciales) y usa un
     secreto que tiene otros usos; contradice "nunca compartir un mismo secreto entre dos propósitos"
     (`context/08 §8`).
7. **XChaCha20-Poly1305 de PyNaCl/libsodium.**
   - Pros: nonce de 192 bits, sin límite práctico de mensajes.
   - Contras: dependencia nueva (`C-13`) para resolver un límite que con este volumen no existe.

## Decisión
Opción 1. Detalle de implementación en `specs/04-integration-management/design.md §3.4`, §5 y §10.

1. **Algoritmo y librería.** AES-256-GCM con `cryptography.hazmat.primitives.ciphers.aead.AESGCM`, de
   `cryptography==50.0.2` (ya fijada, sin dependencia nueva). Nonce de 96 bits de `os.urandom` por cada cifrado;
   nunca se reutiliza un nonce con la misma clave (cada cifrado genera uno nuevo, también en un re-cifrado).
2. **Qué se cifra (Q-401, Q-405).** Solo los valores de los campos que el esquema del adaptador marca **secretos**,
   serializados como JSON canónico (UTF-8, claves ordenadas), en un único texto cifrado por juego. Los campos no
   secretos del juego (p. ej. una public key) y la configuración se guardan en claro, porque se muestran completos a
   `owner`/`admin`. Los **nombres** de los campos secretos configurados se guardan en claro (no son secretos) para
   mostrar "configurado". Límite de 16 KiB de texto plano por juego.
3. **Sobre y datos asociados.** Columnas de la fila del juego: `key_id` (texto corto, no secreto), `format_version`
   (`1`) y `ciphertext` (`bytea` = nonce ‖ texto cifrado ‖ tag de 16 bytes). El AAD es
   `b"cpu:integration-credentials:v1|" + organization_id + "|" + integration_id + "|" + key_id` (UUID en su forma
   canónica). Descifrar con otra organización, otra integración u otro `key_id` falla con error de autenticación del
   tag, que se traduce a un error interno tipado sin detalle (`CredentialDecryptError`); nunca se intenta "otra
   clave" a ciegas: se usa la del `key_id` de la fila.
4. **Clave maestra fuera del repo y de la base.** El llavero viene del entorno del proceso, nunca de la base, del
   repo, de `env.example` ni de un fixture:
   - `INTEGRATIONS_CREDENTIAL_KEYS`: lista `id:clave` separada por comas, cada clave de 32 bytes en base64url; ids
     `^[a-z0-9-]{1,32}$`, sin repetir.
   - `INTEGRATIONS_CREDENTIAL_ACTIVE_KEY`: id de la clave con la que se cifra todo lo nuevo; tiene que estar en la
     lista.
   Se cargan una vez al arrancar con `pydantic-settings` como `SecretStr` (no salen en `repr` de settings ni en
   tracebacks) y se validan: si faltan, una clave no decodifica a 32 bytes, hay ids repetidos o el id activo no
   está, el proceso **no arranca** (`ImproperlyConfigured`) con ningún settings salvo `test`, que usa un llavero
   sintético fijo, solo de test; un *system check* de `prod` rechaza el id reservado `test`. En desarrollo cada
   persona genera su clave con el comando de abajo y la pone en su `.env` (`env.example` trae solo los nombres). En producción la clave
   llega como secreto del orquestador (Docker secret o variable del servicio, a definir con el hosting, Q-065); nunca
   como argumento de línea de comando. Los nombres de las variables contienen `credential`, así que la redacción de
   logs (`apps/common/domain/redaction.py`) los tapa además por nombre.
   Un comando `integrations_generate_key` imprime una clave nueva **una sola vez** en `stdout` (no pasa por el logger)
   para cargarla en el entorno; no la guarda.
5. **Rotación sin downtime (Q-418 a)).**
   1. Se agrega la clave nueva `K2` al llavero de **todos** los procesos (web, worker, beat) sin cambiar la activa;
      se despliega. Todos pueden leer `K1` y `K2`.
   2. Se cambia `INTEGRATIONS_CREDENTIAL_ACTIVE_KEY` a `K2`; se despliega. Desde ahí todo alta, reemplazo o
      reactivación cifra con `K2`; lo guardado con `K1` se sigue leyendo con `K1` (cada fila dice su `key_id`).
   3. El operador corre `manage.py integrations_reencrypt_credentials --operator <email> [--batch-size N]
      [--dry-run]`: recorre los juegos con `key_id` distinto del activo, por organización y en lotes; cada juego se
      re-cifra en su propia transacción corta (lock de la fila, descifrar con su clave, cifrar con la activa, una
      sola `UPDATE` de `ciphertext` + `key_id`), así que una resolución concurrente ve el juego viejo completo o el
      nuevo completo (RN-INT-06). No cambia `credentials_updated_at` (no es un reemplazo de credenciales) ni llama al
      proveedor. Es idempotente y se puede cortar y retomar.
   4. `integrations_reencrypt_credentials --check` informa cuántos juegos quedan por clave y termina con código
      distinto de cero mientras quede alguno con una clave que no es la activa.
   5. Con `--check` en cero, se quita `K1` del llavero; se despliega.
   Rollback en cualquier paso: volver al despliegue anterior con el llavero anterior; mientras `K1` siga en el
   llavero, nada queda ilegible. Una fila con un `key_id` que no está en el llavero no se puede leer: la resolución
   falla con `CredentialKeyUnavailable` (error interno, log `integrations.cipher_key_missing` con
   `integration_id` y `cipher_key_id`, nunca la clave) y la integración no pasa a "credenciales inválidas" (no es
   culpa del proveedor).
   **Clave comprometida:** se rota igual, pero rotar la clave maestra no protege lo que ya se filtró: si se filtraron
   la base **y** la clave, los dueños tienen que regenerar sus tokens en el proveedor y reemplazarlos en el Hub.
6. **Auditoría sin secretos (`C-08`).** El re-cifrado emite, por organización, `integration.credentials_reencrypted`
   con la cantidad de juegos y los ids de clave origen y destino (no secretos), actor el operador de plataforma
   (`AuditActor.platform_operator`), como los demás comandos (SPEC-02 §4.5). Ningún evento lleva valores de
   credenciales, texto cifrado, nonce ni clave. Los demás eventos del módulo (alta, reemplazo, desconexión) tampoco.
7. **Resolución just-in-time (RN-INT-05, RN-ENG-08).** Las credenciales se descifran dentro de la función que arma el
   `IntegrationContext` de **una** operación y se entregan al motor dentro del tipo de credenciales de SPEC-03, cuyo
   `repr`/`str` no muestra valores; no se cachean entre operaciones ni se guardan en el `ContextVar`, la sesión,
   Celery ni Redis. Python no permite borrar un `str` de memoria: se acepta, y se minimiza su vida.
8. **Lo que no se cifra y por qué.** El identificador de cuenta del proveedor (no secreto, Q-403), los campos no
   secretos (Q-405) y el **identificador de ruteo de webhooks** (Q-415): este último es un valor aleatorio de 256
   bits que identifica la integración en la URL de webhooks, no autentica (la autenticidad la da la firma, `C-07`),
   se tiene que mostrar a `owner`/`admin` cada vez que lo piden y se busca por igualdad desde SPEC-07. Se guarda en
   claro con índice único y nunca se loguea (las rutas se loguean por plantilla, Q-041).

## Consecuencias
- **Se gana:** credenciales ilegibles para quien tenga solo la base (o un backup); un texto cifrado copiado entre
  organizaciones o integraciones no se descifra (AAD); rotación sin downtime con progreso medible por `key_id`;
  ninguna dependencia nueva; el formato (`format_version` + `key_id`) admite migrar a cifrado de sobre con KMS sin
  cambiar el esquema: la versión 2 guardaría la clave de datos envuelta en la misma fila.
- **Se paga:** un sobre propio que hay que revisar con cuidado (tests de vectores, de AAD cruzado y de nonce nuevo
  por cifrado); la clave maestra es un secreto más que el operador tiene que guardar **aparte** de los backups de la
  base: si se pierde, todas las credenciales quedan ilegibles y los dueños tienen que cargarlas de nuevo (no se
  pierde dinero ni cobros: los cobros `pending` no se podrían consultar hasta recargarlas). Se anota en el checklist
  de release.
- **Pendiente:**
  - Dónde vive la clave en producción (Docker secret, variable del servicio o KMS) se decide con el hosting (Q-020,
    Q-065); si se elige KMS, es un ADR que reemplaza el punto 4 y agrega la versión 2 del sobre.
  - Refresh tokens de OAuth (Q-014, antes de abrir a terceros): se guardarán como un campo secreto más del juego, con
    este mismo esquema; su renovación es otra spec.
  - Cuando SPEC-10 tenga el sink transaccional de auditoría, el evento del re-cifrado pasa a ser durable (mismo gate
    de producción que SPEC-02 §10).
