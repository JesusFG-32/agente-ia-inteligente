"""
app.py
======
API REST Flask 3.0 del Agente IA de Monitoreo.
Expone endpoints para métricas, análisis IA, chat y control de servicios.
"""

import logging
from datetime import datetime

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

import config
from adaptadores import AdaptadorMariaDB, AdaptadorNginx, BaseDatos, AdaptadorMongoDB
from agente import AgenteIA

# ─── Setup ────────────────────────────────────────────────────
logger = logging.getLogger("agente-ia.app")

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
CORS(app)

# ─── Inicializar servicios (lazy) ─────────────────────────────
_db: BaseDatos | None = None
_mongodb: AdaptadorMongoDB | None = None
_agente: AgenteIA | None = None
_nginx: AdaptadorNginx | None = None
_mariadb: AdaptadorMariaDB | None = None


def get_db() -> BaseDatos | None:
    global _db
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
        try:
            _agente = AgenteIA(db=get_db(), mongodb=get_mongodb())
        except Exception as e:
            logger.error("No se pudo inicializar AgenteIA: %s", e)
    return _agente


def get_nginx() -> AdaptadorNginx | None:
    global _nginx
    if _nginx is None and config.VPS_HOST:
        try:
            _nginx = AdaptadorNginx(
                host=config.VPS_HOST,
                user=config.VPS_USER,
                key_path=config.VPS_KEY_PATH,
                port=config.VPS_PORT,
            )
        except Exception as e:
            logger.error("No se pudo conectar SSH para Nginx: %s", e)
    return _nginx


def get_mariadb() -> AdaptadorMariaDB | None:
    global _mariadb
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
    """Sirve el dashboard principal."""
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health():
    """
    GET /api/health
    Verifica el estado general del agente y sus conexiones.
    """
    estado = {
        "servicio": "agente-ia-inteligente",
        "version": "1.0.0",
        "estado": "operativo",
        "componentes": {
            "gemini": bool(config.GEMINI_API_KEY),
            "postgres": False,
            "mongodb": False,
            "nginx_ssh": bool(config.VPS_HOST),
            "mariadb": bool(config.MARIADB_HOST),
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

    logger.info("Health check solicitado")
    return respuesta_ok({"health": estado})


@app.route("/api/metricas/nginx", methods=["GET"])
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


@app.route("/api/analizar", methods=["POST"])
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
        if nginx:
            metricas["nginx"] = nginx.obtener_metricas()
        if mariadb:
            metricas["mariadb"] = mariadb.obtener_metricas()

    if not metricas:
        return respuesta_error("No hay métricas disponibles para analizar", 400)

    try:
        resultado = agente.analizar_metricas(metricas)
        return respuesta_ok({"analisis": resultado})
    except Exception as e:
        logger.error("Error en /api/analizar: %s", e)
        return respuesta_error(str(e))


@app.route("/api/preguntas", methods=["POST"])
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

        else:
            return respuesta_error(f"Acción desconocida: '{accion}'", 400)

        # Registrar la acción en BD
        if db:
            db.guardar_accion(
                tipo=accion,
                descripcion=f"Acción ejecutada: {accion}",
                parametros=parametros,
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
