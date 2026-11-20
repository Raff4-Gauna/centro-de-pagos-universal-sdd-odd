# 2026-11-20 — memberships-order-test

- **Nivel:** O0
- **Intención:** que `test_AC_TEN_34_owner_and_admin_list` deje de fallar a veces en Windows, sin aflojar lo que prueba.
- **Alcance esperado:** un solo archivo de test, `backend/tests/tenancy/api/test_memberships.py`. No toca código de producción.
- **Cómo se verifica:** el test pasa 20 corridas seguidas en Windows y el resto de `test_memberships.py` sigue en verde.

## Qué se hizo
- **Causa:** el test esperaba las filas en el orden en que se crearon. El listado ordena por `("created_at", "id")` (`selectors/memberships.py:114`). En Windows, `datetime.now()` tiene una resolución gruesa, así que las dos memberships pueden quedar con el mismo `created_at`. En ese caso desempata el `id`, que es un UUID al azar, y el orden sale distinto según la corrida. En Linux (CI) el reloj tiene microsegundos y el problema no aparece.
- **Arreglo:** el test calcula el orden esperado con la misma regla del selector, `(created_at, id)`, en vez de suponer el orden de creación. La forma del subobjeto `user` se busca por id de fila. El test sigue probando el orden del listado.
  - En Python, el orden de los UUID como texto en minúsculas coincide con el orden de PostgreSQL.

## Resultado
Hecho. Ver el PR de la rama `log/2026-11-20-memberships-order-test`.

## Preguntas nuevas (Q-xxx)
Ninguna.
