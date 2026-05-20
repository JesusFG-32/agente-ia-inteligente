"""
config.py - Configuración central del Agente IA
================================================
Carga variables de entorno y expone configuración global.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# ─── Cargar .env ────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ─── Logging setup ──────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("agente-ia")


# ─── Google Gemini ───────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-pro")

# ─── VPS / SSH ───────────────────────────────────────────────
VPS_HOST: str = os.getenv("VPS_HOST", "")
VPS_USER: str = os.getenv("VPS_USER", "ubuntu")
VPS_KEY_PATH: str = str(BASE_DIR / os.getenv("VPS_KEY_PATH", "keys/id_rsa"))
VPS_PORT: int = int(os.getenv("VPS_PORT", "22"))

# ─── PostgreSQL ──────────────────────────────────────────────
DB_HOST: str = os.getenv("DB_HOST", "localhost")
DB_PORT: int = int(os.getenv("DB_PORT", "5432"))
DB_NAME: str = os.getenv("DB_NAME", "agente_ia")
DB_USER: str = os.getenv("DB_USER", "postgres")
DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")

# ─── MariaDB ─────────────────────────────────────────────────
MARIADB_HOST: str = os.getenv("MARIADB_HOST", "")
MARIADB_PORT: int = int(os.getenv("MARIADB_PORT", "3306"))
MARIADB_USER: str = os.getenv("MARIADB_USER", "root")
MARIADB_PASSWORD: str = os.getenv("MARIADB_PASSWORD", "")

# ─── Flask ───────────────────────────────────────────────────
FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
FLASK_DEBUG: bool = os.getenv("FLASK_DEBUG", "True").lower() == "true"
FLASK_PORT: int = int(os.getenv("FLASK_PORT", "5000"))
SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")

# ─── Validación de configuración crítica ─────────────────────
def validar_config() -> list[str]:
    """
    Verifica que las variables críticas estén definidas.
    Retorna lista de advertencias.
    """
    advertencias = []
    if not GEMINI_API_KEY:
        advertencias.append("⚠️  GEMINI_API_KEY no configurada")
    if not VPS_HOST:
        advertencias.append("⚠️  VPS_HOST no configurado (SSH deshabilitado)")
    if not DB_PASSWORD:
        advertencias.append("⚠️  DB_PASSWORD vacía (revisa configuración PostgreSQL)")
    if SECRET_KEY == "dev-secret-key-change-in-production":
        advertencias.append("⚠️  SECRET_KEY por defecto — cambia en producción")
    return advertencias


if __name__ == "__main__":
    problemas = validar_config()
    if problemas:
        for p in problemas:
            logger.warning(p)
    else:
        logger.info("✅ Configuración válida")
