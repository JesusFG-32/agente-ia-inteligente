"""
auth.py
=======
Módulo de autenticación y autorización del Agente IA.

Funcionalidades:
    - Generación determinística de UUID v5 a partir del email
    - Hash de contraseñas con bcrypt
    - Emisión y verificación de tokens JWT
    - Sistema de roles (admin / operator / viewer)
    - Permisos granulares por endpoint
    - Decoradores Flask: @requiere_auth, @requiere_rol, @requiere_permiso
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional

import bcrypt
import jwt
from flask import g, jsonify, request

import config

logger = logging.getLogger("agente-ia.auth")

# ─── Definición de roles y permisos granulares ──────────────

# Catálogo de permisos disponibles. Cada endpoint protegido referencia uno.
PERMISOS = {
    "view_dashboard":    "Acceder al dashboard web",
    "read_metrics":      "Leer métricas de Nginx y MariaDB",
    "read_events":       "Leer historial de eventos",
    "read_actions":      "Leer historial de acciones",
    "use_ai_chat":       "Chatear con el agente IA",
    "analyze_anomalies": "Solicitar análisis de anomalías a la IA",
    "execute_actions":   "Ejecutar acciones de control (reiniciar, optimizar, kill)",
    "manage_users":      "CRUD de usuarios y roles",
}

# Asignación de permisos por rol.
# admin:    todos los permisos
# operator: todo salvo gestionar usuarios
# viewer:   solo lectura + chat IA
ROLES = {
    "admin": set(PERMISOS.keys()),
    "operator": {
        "view_dashboard", "read_metrics", "read_events", "read_actions",
        "use_ai_chat", "analyze_anomalies", "execute_actions",
    },
    "viewer": {
        "view_dashboard", "read_metrics", "read_events", "read_actions",
        "use_ai_chat",
    },
}

ROLES_VALIDOS = tuple(ROLES.keys())


# ─── UUID v5 determinístico ──────────────────────────────────

def _namespace_uuid() -> uuid.UUID:
    """Convierte el namespace de config a un objeto UUID válido."""
    try:
        return uuid.UUID(config.UUID_NAMESPACE)
    except (ValueError, AttributeError) as e:
        logger.error("UUID_NAMESPACE inválido: %s — usando NAMESPACE_DNS de fallback", e)
        return uuid.NAMESPACE_DNS


def generar_uuid_v5(email: str) -> str:
    """
    Genera un UUID v5 determinístico a partir del email del usuario.

    El mismo email + mismo namespace siempre produce el mismo UUID.
    Esto facilita migraciones y evita duplicados por email.

    Args:
        email: Email del usuario (se normaliza a minúsculas + trim).

    Returns:
        String UUID v5 (e.g. "a3b2c1d0-...").
    """
    email_normalizado = (email or "").strip().lower()
    if not email_normalizado:
        raise ValueError("Email requerido para generar UUID v5")
    return str(uuid.uuid5(_namespace_uuid(), email_normalizado))


# ─── Hash de contraseñas (bcrypt) ────────────────────────────

def hash_password(password: str) -> str:
    """
    Genera un hash bcrypt seguro de la contraseña.

    Args:
        password: Contraseña en texto plano (mínimo 8 caracteres recomendado).

    Returns:
        Hash bcrypt como string UTF-8 (incluye salt).
    """
    if not password or len(password) < 6:
        raise ValueError("La contraseña debe tener al menos 6 caracteres")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verificar_password(password: str, hash_almacenado: str) -> bool:
    """
    Verifica si una contraseña en texto plano coincide con su hash bcrypt.

    Args:
        password: Contraseña en texto plano.
        hash_almacenado: Hash bcrypt previamente generado.

    Returns:
        True si coincide, False en caso contrario.
    """
    if not password or not hash_almacenado:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hash_almacenado.encode("utf-8"),
        )
    except (ValueError, TypeError) as e:
        logger.warning("Error verificando password: %s", e)
        return False


# ─── JWT (JSON Web Tokens) ───────────────────────────────────

def generar_token(usuario: dict) -> str:
    """
    Genera un token JWT firmado para el usuario.

    Args:
        usuario: dict con al menos id, email, username, rol.

    Returns:
        Token JWT como string.
    """
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario["id"]),
        "email": usuario["email"],
        "username": usuario["username"],
        "rol": usuario["rol"],
        "iat": ahora,
        "exp": ahora + timedelta(hours=config.JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def verificar_token(token: str) -> Optional[dict]:
    """
    Decodifica y valida un JWT.

    Args:
        token: Token JWT (sin el prefijo "Bearer ").

    Returns:
        Payload del token si es válido, None en caso contrario.
    """
    if not token:
        return None
    try:
        return jwt.decode(token, config.JWT_SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.info("Token expirado")
        return None
    except jwt.InvalidTokenError as e:
        logger.info("Token inválido: %s", e)
        return None


def _extraer_token() -> Optional[str]:
    """Obtiene el token del header Authorization: Bearer <token>."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return None


# ─── Decoradores Flask ───────────────────────────────────────

def requiere_auth(funcion):
    """
    Decorador: exige un JWT válido. Adjunta el usuario decodificado a flask.g.usuario.

    Uso:
        @app.route("/protegido")
        @requiere_auth
        def vista():
            return g.usuario["email"]
    """
    @wraps(funcion)
    def wrapper(*args, **kwargs):
        token = _extraer_token()
        payload = verificar_token(token)
        if payload is None:
            return jsonify({
                "ok": False,
                "error": "Token inválido o expirado",
                "timestamp": datetime.now().isoformat(),
            }), 401
        g.usuario = payload
        return funcion(*args, **kwargs)
    return wrapper


def requiere_rol(*roles_permitidos: str):
    """
    Decorador: el usuario debe tener uno de los roles indicados.

    Uso:
        @requiere_auth
        @requiere_rol("admin")
        def solo_admin(): ...
    """
    def decorator(funcion):
        @wraps(funcion)
        def wrapper(*args, **kwargs):
            usuario = getattr(g, "usuario", None)
            if not usuario:
                return jsonify({"ok": False, "error": "No autenticado"}), 401
            if usuario.get("rol") not in roles_permitidos:
                logger.warning(
                    "Acceso denegado: %s (rol=%s) intentó acceder a recurso restringido a %s",
                    usuario.get("email"), usuario.get("rol"), roles_permitidos,
                )
                return jsonify({
                    "ok": False,
                    "error": f"Rol insuficiente. Requerido: {', '.join(roles_permitidos)}",
                }), 403
            return funcion(*args, **kwargs)
        return wrapper
    return decorator


def requiere_permiso(permiso: str):
    """
    Decorador: el rol del usuario debe incluir el permiso granular indicado.

    Uso:
        @requiere_auth
        @requiere_permiso("execute_actions")
        def reiniciar(): ...
    """
    if permiso not in PERMISOS:
        raise ValueError(f"Permiso desconocido: {permiso}")

    def decorator(funcion):
        @wraps(funcion)
        def wrapper(*args, **kwargs):
            usuario = getattr(g, "usuario", None)
            if not usuario:
                return jsonify({"ok": False, "error": "No autenticado"}), 401
            rol = usuario.get("rol", "")
            permisos_rol = ROLES.get(rol, set())
            if permiso not in permisos_rol:
                logger.warning(
                    "Permiso denegado: %s (rol=%s) intentó usar %s",
                    usuario.get("email"), rol, permiso,
                )
                return jsonify({
                    "ok": False,
                    "error": f"Permiso insuficiente. Se requiere: {permiso}",
                }), 403
            return funcion(*args, **kwargs)
        return wrapper
    return decorator


# ─── Helpers ─────────────────────────────────────────────────

def usuario_actual() -> Optional[dict]:
    """Retorna el usuario autenticado actual desde flask.g (o None)."""
    return getattr(g, "usuario", None)


def permisos_del_rol(rol: str) -> list[str]:
    """Lista los permisos asociados a un rol."""
    return sorted(ROLES.get(rol, set()))
