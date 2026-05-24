"""
seed_admin.py
=============
Crea el primer usuario administrador del Agente IA.

Uso:
    1) Configura ADMIN_EMAIL, ADMIN_USERNAME y ADMIN_PASSWORD en .env
    2) Ejecuta: python seed_admin.py

Si el admin ya existe, el script no hace nada (idempotente).
También permite crear usuarios extra via CLI:
    python seed_admin.py --email demo@x.com --username demo --password 12345678 --rol operator
"""

import argparse
import logging
import sys

import auth
import config
from adaptadores.postgres import BaseDatos

logger = logging.getLogger("agente-ia.seed")


def crear_o_actualizar(
    db: BaseDatos,
    email: str,
    username: str,
    password: str,
    rol: str,
) -> int:
    """
    Crea un usuario o lo reporta si ya existe.

    Returns:
        0 si se creó o ya existía, 1 si hubo error.
    """
    if rol not in auth.ROLES_VALIDOS:
        logger.error("Rol inválido: '%s'. Válidos: %s", rol, auth.ROLES_VALIDOS)
        return 1
    if len(password) < 6:
        logger.error("La contraseña debe tener al menos 6 caracteres")
        return 1

    usuario_id = auth.generar_uuid_v5(email)
    existente = db.obtener_usuario_por_email(email)
    if existente:
        logger.info("ℹ️  Usuario '%s' ya existe (id=%s, rol=%s) — sin cambios",
                    email, existente["id"], existente["rol"])
        return 0

    password_hash = auth.hash_password(password)
    nuevo = db.crear_usuario(usuario_id, email, username, password_hash, rol, True)
    if nuevo is None:
        logger.error("❌ No se pudo crear el usuario '%s' (¿username duplicado?)", email)
        return 1

    logger.info("✅ Usuario creado: %s (rol=%s, id=%s)", email, rol, nuevo["id"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed de usuarios del Agente IA")
    parser.add_argument("--email", help="Email del usuario (default: ADMIN_EMAIL de .env)")
    parser.add_argument("--username", help="Username (default: ADMIN_USERNAME de .env)")
    parser.add_argument("--password", help="Password (default: ADMIN_PASSWORD de .env)")
    parser.add_argument("--rol", default="admin", choices=auth.ROLES_VALIDOS)
    args = parser.parse_args()

    email = args.email or config.ADMIN_EMAIL
    username = args.username or config.ADMIN_USERNAME
    password = args.password or config.ADMIN_PASSWORD

    if not password:
        logger.error("❌ ADMIN_PASSWORD no configurada. Define ADMIN_PASSWORD en .env "
                     "o pásala con --password")
        return 1

    try:
        db = BaseDatos(
            host=config.DB_HOST, port=config.DB_PORT, database=config.DB_NAME,
            user=config.DB_USER, password=config.DB_PASSWORD,
        )
    except Exception as e:
        logger.error("❌ No se pudo conectar a PostgreSQL: %s", e)
        return 1

    return crear_o_actualizar(db, email, username, password, args.rol)


if __name__ == "__main__":
    sys.exit(main())
