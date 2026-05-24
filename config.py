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

# ─── MongoDB ─────────────────────────────────────────────────
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "agente_ia_chats")
MONGO_COLLECTION_NAME: str = os.getenv("MONGO_COLLECTION_NAME", "conversaciones")

# ─── Autenticación JWT ───────────────────────────────────────
JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "jwt-dev-secret-change-in-production")
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "8"))

# UUID v5 namespace — identificador único del proyecto para generar IDs determinísticos.
# Si lo cambias, los UUIDs generados para los mismos emails cambiarán también.
UUID_NAMESPACE: str = os.getenv(
    "UUID_NAMESPACE",
    "a7c8e9f0-1b2c-5d3e-9f4a-5b6c7d8e9f0a",
)

# Credenciales del primer admin (usadas por seed_admin.py)
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@agente-ia.local")
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

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
    if not MONGO_URI:
        advertencias.append("⚠️  MONGO_URI no configurado (MongoDB deshabilitado, se usará memoria)")
    if JWT_SECRET_KEY == "jwt-dev-secret-change-in-production":
        advertencias.append("⚠️  JWT_SECRET_KEY por defecto — cambia en producción")
    if not ADMIN_PASSWORD:
        advertencias.append("ℹ️  ADMIN_PASSWORD no configurada — necesaria para seed_admin.py")
    return advertencias


if __name__ == "__main__":
    problemas = validar_config()
    if problemas:
        for p in problemas:
            logger.warning(p)
    else:
        logger.info("✅ Configuración válida")
