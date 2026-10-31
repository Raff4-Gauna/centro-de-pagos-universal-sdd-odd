# mpqr/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

# ──────────────────── Cargar .env ──────────────────────
# Coloca el .env en la raíz del proyecto (junto a requirements.txt)
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)

# ──────────────────── Helper sencillo ──────────────────
def get(key: str, fallback=None):
    """
    Devuelve el valor de la variable del entorno `key`.
    - Busca primero en variables ya cargadas por el sistema.
    - Luego en el .env que se cargó con `load_dotenv`.
    - Si no existe, devuelve `fallback`.
    """
    return os.getenv(key.upper(), fallback)
