"""
app.py
======
API REST Flask 3.0 del Agente IA de Monitoreo.
Expone endpoints para métricas, análisis IA, chat y control de servicios.
"""

import logging
from datetime import datetime

from flask import Flask, g, jsonify, render_template, request
from flask_cors import CORS

import auth
import config
from adaptadores import AdaptadorMariaDB, AdaptadorNginx, BaseDatos, AdaptadorMongoDB, AdaptadorSistema, AdaptadorDocker
from agente import AgenteIA

# ─── Setup ────────────────────────────────────────────────────
import sys
import os

logger = logging.getLogger("agente-ia.app")

if getattr(sys, 'frozen', False):
    # Si corre empaquetado en un ejecutable (.exe), busca carpetas al lado del ejecutable
    base_dir = os.path.dirname(sys.executable)
else:
    # En desarrollo normal
    base_dir = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(base_dir, "templates"),
    static_folder=os.path.join(base_dir, "static"),
)
app.secret_key = config.SECRET_KEY
CORS(app)

# ─── Inicializar servicios (lazy) ─────────────────────────────
import threading

_db: BaseDatos | None = None
_mongodb: AdaptadorMongoDB | None = None
_agente: AgenteIA | None = None
_nginx: AdaptadorNginx | None = None
_mariadb: AdaptadorMariaDB | None = None
_sistema: AdaptadorSistema | None = None
_docker: AdaptadorDocker | None = None

_lock_db = threading.Lock()
_lock_mongodb = threading.Lock()
_lock_agente = threading.Lock()
_lock_nginx = threading.Lock()
_lock_mariadb = threading.Lock()
_lock_sistema = threading.Lock()
_lock_docker = threading.Lock()


def get_docker() -> AdaptadorDocker | None:
    global _docker
    if _docker is None:
        with _lock_docker:
            if _docker is None:
                try:
                    nginx = get_nginx()
                    ssh_client = nginx._cliente if nginx else None
                    _docker = AdaptadorDocker(
                        host=config.VPS_HOST,
                        user=config.VPS_USER,
                        key_path=config.VPS_KEY_PATH,
                        password=config.VPS_PASSWORD,
                        auth_method=config.VPS_AUTH_METHOD,
                        port=config.VPS_PORT,
                        ssh_client=ssh_client,
                    )
                except Exception as e:
                    logger.error("No se pudo conectar SSH para Docker: %s", e)
    return _docker


def get_sistema() -> AdaptadorSistema | None:
    global _sistema
    if _sistema is None:
        with _lock_sistema:
            if _sistema is None:
                try:
                    # Reutiliza el cliente SSH de Nginx si está disponible para no duplicar conexiones SSH
                    nginx = get_nginx()
                    ssh_client = nginx._cliente if nginx else None
                    _sistema = AdaptadorSistema(
                        host=config.VPS_HOST,
                        user=config.VPS_USER,
                        key_path=config.VPS_KEY_PATH,
                        password=config.VPS_PASSWORD,
                        auth_method=config.VPS_AUTH_METHOD,
                        port=config.VPS_PORT,
                        ssh_client=ssh_client,
                    )
                except Exception as e:
                    logger.error("No se pudo conectar SSH para Sistema: %s", e)
    return _sistema


def get_db() -> BaseDatos | None:
    global _db
    if _db is None:
        with _lock_db:
            if _db is None:
                try:
                    _db = BaseDatos(
                        host=config.DB_HOST,
                        port=config.DB_PORT,
                        database=config.DB_NAME,
                        user=config.DB_USER,
                        password=config.DB_PASSWORD,
                    )
                except Exception as e:
                    logger.error("No se pudo conectar a PostgreSQL: %s", e)
    return _db


def get_mongodb() -> AdaptadorMongoDB | None:
    global _mongodb
    if _mongodb is None and config.MONGO_URI:
        with _lock_mongodb:
            if _mongodb is None and config.MONGO_URI:
                try:
                    _mongodb = AdaptadorMongoDB(
                        uri=config.MONGO_URI,
                        db_name=config.MONGO_DB_NAME,
                        collection_name=config.MONGO_COLLECTION_NAME,
                    )
                except Exception as e:
                    logger.error("No se pudo conectar a MongoDB: %s", e)
    return _mongodb


def get_agente() -> AgenteIA | None:
    global _agente
    if _agente is None:
        with _lock_agente:
            if _agente is None:
                try:
                    _agente = AgenteIA(db=get_db(), mongodb=get_mongodb())
                except Exception as e:
                    logger.error("No se pudo inicializar AgenteIA: %s", e)
    return _agente


def get_nginx() -> AdaptadorNginx | None:
    global _nginx
    if _nginx is None and config.VPS_HOST:
        with _lock_nginx:
            if _nginx is None and config.VPS_HOST:
                try:
                    _nginx = AdaptadorNginx(
                        host=config.VPS_HOST,
                        user=config.VPS_USER,
                        key_path=config.VPS_KEY_PATH,
                        password=config.VPS_PASSWORD,
                        auth_method=config.VPS_AUTH_METHOD,
                        port=config.VPS_PORT,
                    )
                except Exception as e:
                    logger.error("No se pudo conectar SSH para Nginx: %s", e)
    return _nginx


def get_mariadb() -> AdaptadorMariaDB | None:
    global _mariadb
    if _mariadb is None and config.MARIADB_HOST:
        with _lock_mariadb:
            if _mariadb is None and config.MARIADB_HOST:
                try:
                    _mariadb = AdaptadorMariaDB(
                        host=config.MARIADB_HOST,
                        user=config.MARIADB_USER,
                        password=config.MARIADB_PASSWORD,
                        port=config.MARIADB_PORT,
                    )
                except Exception as e:
                    logger.error("No se pudo conectar a MariaDB: %s", e)
    return _mariadb


# ─── Helpers ──────────────────────────────────────────────────

def respuesta_ok(datos: dict, codigo: int = 200):
    return jsonify({"ok": True, "timestamp": datetime.now().isoformat(), **datos}), codigo


def respuesta_error(mensaje: str, codigo: int = 500):
    return jsonify({"ok": False, "error": mensaje, "timestamp": datetime.now().isoformat()}), codigo


# ─── Rutas ────────────────────────────────────────────────────

@app.route("/")
def index():
    """Sirve el dashboard principal (la auth se valida en el frontend con el JWT)."""
    return render_template("index.html")


@app.route("/login")
def login_page():
    """Página de login."""
    return render_template("login.html")


@app.route("/admin/usuarios")
def admin_usuarios_page():
    """Panel de administración de usuarios (solo admin valida via JWT en frontend)."""
    return render_template("admin_usuarios.html")


# ─── Autenticación ───────────────────────────────────────────

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    """
    POST /api/auth/login
    Body: { "email": "...", "password": "..." }
    Retorna un JWT si las credenciales son válidas.
    """
    datos = request.get_json(silent=True) or {}
    email = (datos.get("email") or "").strip().lower()
    password = datos.get("password") or ""

    if not email or not password:
        return respuesta_error("Email y contraseña son requeridos", 400)

    db = get_db()
    if db is None:
        return respuesta_error("Base de datos no disponible", 503)

    usuario = db.obtener_usuario_por_email(email)
    if usuario is None or not auth.verificar_password(password, usuario["password_hash"]):
        logger.warning("Login fallido: %s", email)
        return respuesta_error("Credenciales inválidas", 401)

    if not usuario.get("activo"):
        return respuesta_error("Cuenta deshabilitada", 403)

    # Convertir UUID a string para JWT
    usuario["id"] = str(usuario["id"])
    token = auth.generar_token(usuario)
    db.registrar_login(usuario["id"])
    db.guardar_evento("login", f"Login exitoso de {email}", "info", {"usuario_id": usuario["id"]})

    return respuesta_ok({
        "token": token,
        "usuario": {
            "id": usuario["id"],
            "email": usuario["email"],
            "username": usuario["username"],
            "rol": usuario["rol"],
            "permisos": auth.permisos_del_rol(usuario["rol"]),
        },
        "expira_en_horas": config.JWT_EXPIRATION_HOURS,
    })


@app.route("/api/auth/me", methods=["GET"])
@auth.requiere_auth
def auth_me():
    """Retorna la info del usuario autenticado actual."""
    usuario = g.usuario
    db = get_db()
    datos_db = db.obtener_usuario_por_id(usuario["sub"]) if db else None
    return respuesta_ok({
        "usuario": {
            "id": usuario["sub"],
            "email": usuario["email"],
            "username": usuario["username"],
            "rol": usuario["rol"],
            "permisos": auth.permisos_del_rol(usuario["rol"]),
            "ultimo_login": datos_db.get("ultimo_login").isoformat() if datos_db and datos_db.get("ultimo_login") else None,
        },
    })


@app.route("/api/auth/cambiar-password", methods=["POST"])
@auth.requiere_auth
def auth_cambiar_password():
    """
    POST /api/auth/cambiar-password
    Body: { "password_actual": "...", "password_nueva": "..." }
    """
    datos = request.get_json(silent=True) or {}
    actual = datos.get("password_actual") or ""
    nueva = datos.get("password_nueva") or ""

    if len(nueva) < 6:
        return respuesta_error("La nueva contraseña debe tener al menos 6 caracteres", 400)

    db = get_db()
    if db is None:
        return respuesta_error("Base de datos no disponible", 503)

    usuario_id = g.usuario["sub"]
    usuario = db.obtener_usuario_por_email(g.usuario["email"])
    if not usuario or not auth.verificar_password(actual, usuario["password_hash"]):
        return respuesta_error("Contraseña actual incorrecta", 401)

    nuevo_hash = auth.hash_password(nueva)
    if not db.cambiar_password(usuario_id, nuevo_hash):
        return respuesta_error("No se pudo actualizar la contraseña", 500)
    return respuesta_ok({"mensaje": "Contraseña actualizada"})


# ─── Gestión de usuarios (solo admin) ────────────────────────

@app.route("/api/usuarios", methods=["GET"])
@auth.requiere_auth
@auth.requiere_permiso("manage_users")
def listar_usuarios():
    """Lista todos los usuarios (admin)."""
    db = get_db()
    if db is None:
        return respuesta_error("Base de datos no disponible", 503)
    usuarios = db.listar_usuarios()
    # Convertir UUIDs y timestamps a string
    for u in usuarios:
        u["id"] = str(u["id"])
        for campo in ("ultimo_login", "creado_en", "actualizado_en"):
            if u.get(campo):
                u[campo] = u[campo].isoformat()
    return respuesta_ok({"usuarios": usuarios, "total": len(usuarios)})


@app.route("/api/usuarios", methods=["POST"])
@auth.requiere_auth
@auth.requiere_permiso("manage_users")
def crear_usuario():
    """
    POST /api/usuarios
    Body: { "email": "...", "username": "...", "password": "...", "rol": "viewer" }
    """
    datos = request.get_json(silent=True) or {}
    email = (datos.get("email") or "").strip().lower()
    username = (datos.get("username") or "").strip()
    password = datos.get("password") or ""
    rol = datos.get("rol") or "viewer"

    if not email or not username or not password:
        return respuesta_error("email, username y password son requeridos", 400)
    if rol not in auth.ROLES_VALIDOS:
        return respuesta_error(f"Rol inválido. Válidos: {auth.ROLES_VALIDOS}", 400)
    if len(password) < 6:
        return respuesta_error("La contraseña debe tener al menos 6 caracteres", 400)

    db = get_db()
    if db is None:
        return respuesta_error("Base de datos no disponible", 503)

    try:
        usuario_id = auth.generar_uuid_v5(email)
        password_hash = auth.hash_password(password)
    except ValueError as e:
        return respuesta_error(str(e), 400)

    nuevo = db.crear_usuario(usuario_id, email, username, password_hash, rol, True)
    if nuevo is None:
        return respuesta_error("No se pudo crear el usuario (¿email o username duplicado?)", 409)

    nuevo["id"] = str(nuevo["id"])
    if nuevo.get("creado_en"):
        nuevo["creado_en"] = nuevo["creado_en"].isoformat()
    return respuesta_ok({"usuario": nuevo}, 201)


@app.route("/api/usuarios/<usuario_id>", methods=["PUT"])
@auth.requiere_auth
@auth.requiere_permiso("manage_users")
def actualizar_usuario(usuario_id: str):
    """
    PUT /api/usuarios/<uuid>
    Body: { "username"?: "...", "rol"?: "...", "activo"?: bool }
    """
    datos = request.get_json(silent=True) or {}
    rol = datos.get("rol")
    if rol is not None and rol not in auth.ROLES_VALIDOS:
        return respuesta_error(f"Rol inválido. Válidos: {auth.ROLES_VALIDOS}", 400)

    # Prevenir que un admin se quite el rol o se deshabilite a sí mismo
    if usuario_id == g.usuario["sub"]:
        if rol is not None and rol != "admin":
            return respuesta_error("No puedes cambiar tu propio rol", 400)
        if datos.get("activo") is False:
            return respuesta_error("No puedes desactivarte a ti mismo", 400)

    db = get_db()
    if db is None:
        return respuesta_error("Base de datos no disponible", 503)

    actualizado = db.actualizar_usuario(
        usuario_id,
        username=datos.get("username"),
        rol=rol,
        activo=datos.get("activo"),
    )
    if actualizado is None:
        return respuesta_error("Usuario no encontrado o conflicto al actualizar", 404)

    actualizado["id"] = str(actualizado["id"])
    for campo in ("ultimo_login", "creado_en", "actualizado_en"):
        if actualizado.get(campo):
            actualizado[campo] = actualizado[campo].isoformat()
    return respuesta_ok({"usuario": actualizado})


@app.route("/api/usuarios/<usuario_id>", methods=["DELETE"])
@auth.requiere_auth
@auth.requiere_permiso("manage_users")
def eliminar_usuario(usuario_id: str):
    """Elimina un usuario. Un admin no puede eliminarse a sí mismo."""
    if usuario_id == g.usuario["sub"]:
        return respuesta_error("No puedes eliminarte a ti mismo", 400)
    db = get_db()
    if db is None:
        return respuesta_error("Base de datos no disponible", 503)
    if not db.eliminar_usuario(usuario_id):
        return respuesta_error("Usuario no encontrado", 404)
    return respuesta_ok({"mensaje": "Usuario eliminado", "id": usuario_id})


@app.route("/api/auth/roles", methods=["GET"])
@auth.requiere_auth
def listar_roles():
    """Retorna los roles disponibles y sus permisos (útil para el panel admin)."""
    return respuesta_ok({
        "roles": {rol: sorted(perms) for rol, perms in auth.ROLES.items()},
        "permisos": auth.PERMISOS,
    })


@app.route("/api/health", methods=["GET"])
def health():
    """
    GET /api/health
    Verifica el estado general del agente y sus conexiones.
    """
    estado = {
        "servicio": "agente-ia-inteligente",
        "version": "1.1.0",
        "estado": "operativo",
        "componentes": {
            "gemini": bool(config.GEMINI_API_KEY),
            "postgres": False,
            "mongodb": False,
            "nginx_ssh": bool(config.VPS_HOST),
            "mariadb": bool(config.MARIADB_HOST),
            "sistema": False,
            "docker": False,
        },
    }
    try:
        db = get_db()
        estado["componentes"]["postgres"] = db is not None
    except Exception:
        pass

    try:
        mongo = get_mongodb()
        estado["componentes"]["mongodb"] = mongo is not None and mongo.activo
    except Exception:
        pass

    try:
        sys = get_sistema()
        estado["componentes"]["sistema"] = sys is not None
    except Exception:
        pass

    try:
        doc = get_docker()
        estado["componentes"]["docker"] = doc is not None
    except Exception:
        pass

    logger.info("Health check solicitado")
    return respuesta_ok({"health": estado})


@app.route("/api/metricas/nginx", methods=["GET"])
@auth.requiere_auth
@auth.requiere_permiso("read_metrics")
def metricas_nginx():
    """
    GET /api/metricas/nginx
    Obtiene métricas actuales de Nginx via SSH.
    """
    nginx = get_nginx()
    if nginx is None:
        return respuesta_error("Adaptador Nginx no disponible. Verifica VPS_HOST en .env", 503)
    try:
        metricas = nginx.obtener_metricas()
        # Guardar métrica de conexiones en BD
        db = get_db()
        if db and metricas.get("ok"):
            conexiones = metricas.get("conexiones", {}).get("total", 0)
            db.guardar_metrica("nginx", "conexiones_activas", conexiones, metricas)
        return respuesta_ok({"metricas": metricas})
    except Exception as e:
        logger.error("Error en /api/metricas/nginx: %s", e)
        return respuesta_error(str(e))


@app.route("/api/metricas/mariadb", methods=["GET"])
@auth.requiere_auth
@auth.requiere_permiso("read_metrics")
def metricas_mariadb():
    """
    GET /api/metricas/mariadb
    Obtiene métricas actuales de MariaDB.
    """
    mariadb = get_mariadb()
    if mariadb is None:
        return respuesta_error("Adaptador MariaDB no disponible. Verifica MARIADB_HOST en .env", 503)
    try:
        metricas = mariadb.obtener_metricas()
        db = get_db()
        if db and metricas.get("ok"):
            conexiones = metricas.get("conexiones", {}).get("total", 0)
            db.guardar_metrica("mariadb", "conexiones_activas", conexiones, metricas)
        return respuesta_ok({"metricas": metricas})
    except Exception as e:
        logger.error("Error en /api/metricas/mariadb: %s", e)
        return respuesta_error(str(e))


@app.route("/api/metricas/sistema", methods=["GET"])
@auth.requiere_auth
@auth.requiere_permiso("read_metrics")
def metricas_sistema():
    """
    GET /api/metricas/sistema
    Obtiene métricas actuales de CPU, RAM y Disco.
    """
    sys = get_sistema()
    if sys is None:
        return respuesta_error("Adaptador Sistema no disponible.", 503)
    try:
        metricas = sys.obtener_metricas()
        db = get_db()
        if db and metricas.get("ok"):
            # Guardar CPU, RAM y Disco en BD
            db.guardar_metrica("sistema", "cpu_uso", metricas.get("cpu", {}).get("porcentaje", 0.0), metricas)
            db.guardar_metrica("sistema", "ram_uso", metricas.get("ram", {}).get("porcentaje", 0.0), metricas)
            db.guardar_metrica("sistema", "disco_uso", metricas.get("disco", {}).get("porcentaje", 0.0), metricas)
        return respuesta_ok({"metricas": metricas})
    except Exception as e:
        logger.error("Error en /api/metricas/sistema: %s", e)
        return respuesta_error(str(e))


@app.route("/api/metricas/docker", methods=["GET"])
@auth.requiere_auth
@auth.requiere_permiso("read_metrics")
def metricas_docker():
    """
    GET /api/metricas/docker
    Obtiene métricas de los contenedores Docker e integra sus recursos.
    """
    doc = get_docker()
    if doc is None:
        return respuesta_error("Adaptador Docker no disponible.", 503)
    try:
        metricas = doc.obtener_metricas()
        db = get_db()
        if db and metricas.get("ok"):
            # Guardar número de contenedores en BD
            resumen = metricas.get("resumen", {})
            db.guardar_metrica("docker", "contenedores_activos", resumen.get("activos", 0), metricas)
            db.guardar_metrica("docker", "contenedores_totales", resumen.get("total", 0), metricas)
        return respuesta_ok({"metricas": metricas})
    except Exception as e:
        logger.error("Error en /api/metricas/docker: %s", e)
        return respuesta_error(str(e))


@app.route("/api/docker/logs", methods=["GET"])
@auth.requiere_auth
@auth.requiere_permiso("read_metrics")
def docker_logs():
    """
    GET /api/docker/logs?contenedor=<id_o_nombre>&lineas=50
    Obtiene los logs de un contenedor específico.
    """
    contenedor = request.args.get("contenedor", "").strip()
    lineas = request.args.get("lineas", 50, type=int)
    if not contenedor:
        return respuesta_error("Se requiere el parámetro 'contenedor'", 400)

    doc = get_docker()
    if doc is None:
        return respuesta_error("Adaptador Docker no disponible.", 503)
    try:
        logs = doc.obtener_logs(contenedor, lineas=lineas)
        return respuesta_ok({"contenedor": contenedor, "logs": logs})
    except Exception as e:
        logger.error("Error en /api/docker/logs: %s", e)
        return respuesta_error(str(e))


@app.route("/api/analizar", methods=["POST"])
@auth.requiere_auth
@auth.requiere_permiso("analyze_anomalies")
def analizar():
    """
    POST /api/analizar
    Envía métricas al agente IA para análisis de anomalías.

    Body JSON (opcional): { "metricas": { ... } }
    Si no se proveen métricas, las obtiene automáticamente.
    """
    agente = get_agente()
    if agente is None:
        return respuesta_error("AgenteIA no disponible. Verifica GEMINI_API_KEY", 503)

    datos = request.get_json(silent=True) or {}
    metricas = datos.get("metricas", {})

    # Si no se proporcionan métricas, obtenerlas automáticamente
    if not metricas:
        nginx = get_nginx()
        mariadb = get_mariadb()
        sys = get_sistema()
        doc = get_docker()
        if nginx:
            metricas["nginx"] = nginx.obtener_metricas()
        if mariadb:
            metricas["mariadb"] = mariadb.obtener_metricas()
        if sys:
            metricas["sistema"] = sys.obtener_metricas()
        if doc:
            metricas["docker"] = doc.obtener_metricas()

    if not metricas:
        return respuesta_error("No hay métricas disponibles para analizar", 400)

    try:
        resultado = agente.analizar_metricas(metricas)
        return respuesta_ok({"analisis": resultado})
    except Exception as e:
        logger.error("Error en /api/analizar: %s", e)
        return respuesta_error(str(e))


@app.route("/api/preguntas", methods=["POST"])
@auth.requiere_auth
@auth.requiere_permiso("use_ai_chat")
def preguntas():
    """
    POST /api/preguntas
    Envía una pregunta al agente IA en lenguaje natural.

    Body JSON: { "pregunta": "¿Cuántas conexiones tiene Nginx?", "session_id": "mi-sesion-123" }
    """
    agente = get_agente()
    if agente is None:
        return respuesta_error("AgenteIA no disponible. Verifica GEMINI_API_KEY", 503)

    datos = request.get_json(silent=True) or {}
    pregunta = datos.get("pregunta", "").strip()
    session_id = datos.get("session_id", "default").strip() or "default"

    if not pregunta:
        return respuesta_error("El campo 'pregunta' es requerido", 400)

    try:
        respuesta = agente.responder_pregunta(pregunta, session_id=session_id)
        # Guardar la interacción en BD (PostgreSQL de auditoría/administración)
        db = get_db()
        if db:
            db.guardar_evento("chat", pregunta, "info", {
                "respuesta": respuesta,
                "session_id": session_id,
            })
        return respuesta_ok({
            "respuesta": respuesta,
            "pregunta": pregunta,
            "session_id": session_id,
        })
    except Exception as e:
        logger.error("Error en /api/preguntas: %s", e)
        return respuesta_error(str(e))


@app.route("/api/eventos", methods=["GET"])
@auth.requiere_auth
@auth.requiere_permiso("read_events")
def eventos():
    """
    GET /api/eventos?limite=50
    Retorna el historial de eventos recientes.
    """
    limite = request.args.get("limite", 50, type=int)
    db = get_db()
    if db is None:
        return respuesta_error("Base de datos no disponible", 503)
    try:
        lista = db.obtener_eventos_recientes(limite=limite)
        return respuesta_ok({"eventos": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /api/eventos: %s", e)
        return respuesta_error(str(e))


@app.route("/api/acciones", methods=["GET"])
@auth.requiere_auth
@auth.requiere_permiso("read_actions")
def acciones():
    """
    GET /api/acciones
    Retorna las acciones automáticas tomadas por el agente.
    """
    db = get_db()
    if db is None:
        return respuesta_error("Base de datos no disponible", 503)
    try:
        lista = db.obtener_acciones_automaticas()
        return respuesta_ok({"acciones": lista, "total": len(lista)})
    except Exception as e:
        logger.error("Error en /api/acciones: %s", e)
        return respuesta_error(str(e))


@app.route("/api/ejecutar-accion", methods=["POST"])
@auth.requiere_auth
@auth.requiere_permiso("execute_actions")
def ejecutar_accion():
    """
    POST /api/ejecutar-accion
    Ejecuta una acción de control sobre los servicios monitoreados.

    Body JSON: { "accion": "reiniciar_nginx" | "optimizar_bd", "parametros": {} }
    """
    datos = request.get_json(silent=True) or {}
    accion = datos.get("accion", "").strip()
    parametros = datos.get("parametros", {})

    if not accion:
        return respuesta_error("El campo 'accion' es requerido", 400)

    db = get_db()
    resultado = {}

    try:
        if accion == "reiniciar_nginx":
            nginx = get_nginx()
            if nginx is None:
                return respuesta_error("Adaptador Nginx no disponible", 503)
            resultado = nginx.reiniciar_nginx()

        elif accion == "optimizar_bd":
            mariadb = get_mariadb()
            if mariadb is None:
                return respuesta_error("Adaptador MariaDB no disponible", 503)
            base_datos = parametros.get("base_datos", "mysql")
            resultado = mariadb.optimizar_tablas(base_datos)

        elif accion == "matar_query":
            mariadb = get_mariadb()
            if mariadb is None:
                return respuesta_error("Adaptador MariaDB no disponible", 503)
            proceso_id = parametros.get("proceso_id")
            if not proceso_id:
                return respuesta_error("Se requiere 'proceso_id' en parámetros", 400)
            resultado = mariadb.matar_query(proceso_id)

        elif accion == "limpiar_logs":
            sys = get_sistema()
            if sys is None:
                return respuesta_error("Adaptador Sistema no disponible", 503)
            resultado = sys.limpiar_logs_vps()

        elif accion == "iniciar_contenedor":
            doc = get_docker()
            if doc is None:
                return respuesta_error("Adaptador Docker no disponible", 503)
            contenedor_id = parametros.get("contenedor_id")
            if not contenedor_id:
                return respuesta_error("Se requiere 'contenedor_id' en parámetros", 400)
            resultado = doc.iniciar_contenedor(contenedor_id)

        elif accion == "detener_contenedor":
            doc = get_docker()
            if doc is None:
                return respuesta_error("Adaptador Docker no disponible", 503)
            contenedor_id = parametros.get("contenedor_id")
            if not contenedor_id:
                return respuesta_error("Se requiere 'contenedor_id' en parámetros", 400)
            resultado = doc.detener_contenedor(contenedor_id)

        elif accion == "reiniciar_contenedor":
            doc = get_docker()
            if doc is None:
                return respuesta_error("Adaptador Docker no disponible", 503)
            contenedor_id = parametros.get("contenedor_id")
            if not contenedor_id:
                return respuesta_error("Se requiere 'contenedor_id' en parámetros", 400)
            resultado = doc.reiniciar_contenedor(contenedor_id)

        else:
            return respuesta_error(f"Acción desconocida: '{accion}'", 400)

        # Registrar la acción en BD (con auditoría del usuario)
        if db:
            usuario_actual = g.usuario
            db.guardar_accion(
                tipo=accion,
                descripcion=f"Acción ejecutada: {accion} por {usuario_actual['email']}",
                parametros={**parametros, "usuario_id": usuario_actual["sub"]},
                resultado=resultado,
                automatica=False,
            )

        return respuesta_ok({"accion": accion, "resultado": resultado})

    except Exception as e:
        logger.error("Error en /api/ejecutar-accion [%s]: %s", accion, e)
        return respuesta_error(str(e))


# ─── Manejadores de error globales ────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return respuesta_error(f"Ruta no encontrada: {request.path}", 404)


@app.errorhandler(405)
def method_not_allowed(e):
    return respuesta_error(f"Método no permitido: {request.method}", 405)


@app.errorhandler(500)
def internal_error(e):
    logger.error("Error interno: %s", e)
    return respuesta_error("Error interno del servidor", 500)


# ─── Punto de entrada ─────────────────────────────────────────

if __name__ == "__main__":
    advertencias = config.validar_config()
    for adv in advertencias:
        logger.warning(adv)

    logger.info("🚀 Iniciando Agente IA en puerto %s", config.FLASK_PORT)
    app.run(
        host="0.0.0.0",
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
