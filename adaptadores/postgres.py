"""
adaptadores/postgres.py
=======================
Gestiona la base de datos PostgreSQL del agente.
Almacena eventos, acciones y métricas históricas.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger("agente-ia.postgres")


class BaseDatos:
    """
    Capa de acceso a PostgreSQL para persistencia del agente IA.

    Tablas gestionadas:
        - eventos      : Anomalías y eventos detectados
        - acciones     : Acciones ejecutadas por el agente
        - metricas     : Historial de métricas recolectadas

    Uso:
        bd = BaseDatos(host="localhost", port=5432, database="agente_ia",
                       user="postgres", password="xxx")
        bd.guardar_evento("anomalia", "CPU alta", "alta", {"cpu": 95})
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
    ) -> None:
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self._conexion: Optional[psycopg2.extensions.connection] = None
        self._conectar()
        self._crear_tablas()

    # ─── Conexión ─────────────────────────────────────────────

    def _conectar(self) -> None:
        """Establece la conexión con PostgreSQL."""
        try:
            self._conexion = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.database,
                user=self.user,
                password=self.password,
                connect_timeout=10,
            )
            self._conexion.autocommit = True
            logger.info("Conectado a PostgreSQL '%s' en %s:%s", self.database, self.host, self.port)
        except psycopg2.Error as e:
            logger.error("Error conectando a PostgreSQL: %s", e)
            raise

    def _cursor(self):
        """Retorna un cursor con factory DictCursor, reconectando si es necesario."""
        try:
            if self._conexion is None or self._conexion.closed:
                self._conectar()
            return self._conexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        except psycopg2.OperationalError:
            self._conectar()
            return self._conexion.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # ─── Creación de tablas ───────────────────────────────────

    def _crear_tablas(self) -> None:
        """Crea las tablas necesarias si no existen."""
        ddl = """
        CREATE TABLE IF NOT EXISTS eventos (
            id          SERIAL PRIMARY KEY,
            tipo        VARCHAR(100) NOT NULL,
            descripcion TEXT,
            severidad   VARCHAR(20) DEFAULT 'info',
            datos       JSONB,
            creado_en   TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS acciones (
            id          SERIAL PRIMARY KEY,
            tipo        VARCHAR(100) NOT NULL,
            descripcion TEXT,
            parametros  JSONB,
            resultado   JSONB,
            automatica  BOOLEAN DEFAULT TRUE,
            creado_en   TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS metricas (
            id          SERIAL PRIMARY KEY,
            origen      VARCHAR(50) NOT NULL,
            nombre      VARCHAR(100) NOT NULL,
            valor       NUMERIC,
            datos       JSONB,
            creado_en   TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS patrones (
            id          SERIAL PRIMARY KEY,
            nombre      VARCHAR(200) NOT NULL,
            descripcion TEXT,
            datos       JSONB,
            ocurrencias INTEGER DEFAULT 1,
            creado_en   TIMESTAMP DEFAULT NOW(),
            actualizado_en TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS usuarios (
            id              UUID PRIMARY KEY,
            email           VARCHAR(255) UNIQUE NOT NULL,
            username        VARCHAR(80)  UNIQUE NOT NULL,
            password_hash   VARCHAR(255) NOT NULL,
            rol             VARCHAR(20)  NOT NULL DEFAULT 'viewer',
            activo          BOOLEAN      NOT NULL DEFAULT TRUE,
            ultimo_login    TIMESTAMP,
            creado_en       TIMESTAMP    DEFAULT NOW(),
            actualizado_en  TIMESTAMP    DEFAULT NOW(),
            CONSTRAINT rol_valido CHECK (rol IN ('admin', 'operator', 'viewer'))
        );
        CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios (email);
        """
        try:
            with self._cursor() as cur:
                cur.execute(ddl)
            logger.info("Tablas verificadas/creadas correctamente")
        except psycopg2.Error as e:
            logger.error("Error creando tablas: %s", e)
            raise

    # ─── Guardar datos ────────────────────────────────────────

    def guardar_evento(
        self,
        tipo: str,
        descripcion: str,
        severidad: str = "info",
        datos: Optional[dict] = None,
    ) -> int:
        """
        Inserta un evento en la base de datos.

        Args:
            tipo: Categoría del evento (e.g. 'anomalia', 'alerta').
            descripcion: Descripción legible del evento.
            severidad: Nivel de severidad ('info', 'warning', 'error', 'critico').
            datos: Datos adicionales en formato dict (se guarda como JSONB).

        Returns:
            ID del evento insertado.
        """
        sql = """
            INSERT INTO eventos (tipo, descripcion, severidad, datos)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (tipo, descripcion, severidad, json.dumps(datos or {})))
                evento_id = cur.fetchone()["id"]
                logger.info("Evento guardado [%s] id=%s sev=%s", tipo, evento_id, severidad)
                return evento_id
        except psycopg2.Error as e:
            logger.error("Error guardando evento: %s", e)
            return -1

    def guardar_accion(
        self,
        tipo: str,
        descripcion: str,
        parametros: Optional[dict] = None,
        resultado: Optional[dict] = None,
        automatica: bool = True,
    ) -> int:
        """
        Registra una acción ejecutada por el agente.

        Args:
            tipo: Tipo de acción (e.g. 'reiniciar_nginx').
            descripcion: Descripción de la acción.
            parametros: Parámetros usados.
            resultado: Resultado obtenido.
            automatica: True si la ejecutó el agente; False si fue manual.

        Returns:
            ID de la acción insertada.
        """
        sql = """
            INSERT INTO acciones (tipo, descripcion, parametros, resultado, automatica)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (
                    tipo, descripcion,
                    json.dumps(parametros or {}),
                    json.dumps(resultado or {}),
                    automatica,
                ))
                accion_id = cur.fetchone()["id"]
                logger.info("Acción guardada [%s] id=%s", tipo, accion_id)
                return accion_id
        except psycopg2.Error as e:
            logger.error("Error guardando acción: %s", e)
            return -1

    def guardar_metrica(
        self,
        origen: str,
        nombre: str,
        valor: float,
        datos: Optional[dict] = None,
    ) -> int:
        """
        Guarda una métrica numérica con metadatos adicionales.

        Args:
            origen: Fuente de la métrica (e.g. 'nginx', 'mariadb').
            nombre: Nombre de la métrica (e.g. 'conexiones_activas').
            valor: Valor numérico de la métrica.
            datos: Contexto adicional.

        Returns:
            ID de la métrica insertada.
        """
        sql = """
            INSERT INTO metricas (origen, nombre, valor, datos)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (origen, nombre, valor, json.dumps(datos or {})))
                metrica_id = cur.fetchone()["id"]
                logger.debug("Métrica guardada [%s.%s]=%s id=%s", origen, nombre, valor, metrica_id)
                return metrica_id
        except psycopg2.Error as e:
            logger.error("Error guardando métrica: %s", e)
            return -1

    # ─── Consultas ────────────────────────────────────────────

    def obtener_eventos_recientes(self, limite: int = 50) -> list[dict]:
        """
        Retorna los N eventos más recientes.

        Args:
            limite: Número máximo de eventos a retornar.

        Returns:
            Lista de eventos ordenados por fecha descendente.
        """
        sql = """
            SELECT id, tipo, descripcion, severidad, datos, creado_en
            FROM eventos
            ORDER BY creado_en DESC
            LIMIT %s
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (limite,))
                filas = cur.fetchall()
                return [dict(f) for f in filas]
        except psycopg2.Error as e:
            logger.error("Error obteniendo eventos: %s", e)
            return []

    def obtener_acciones_automaticas(self, limite: int = 20) -> list[dict]:
        """
        Retorna las últimas acciones ejecutadas automáticamente por el agente.

        Returns:
            Lista de acciones automáticas recientes.
        """
        sql = """
            SELECT id, tipo, descripcion, parametros, resultado, creado_en
            FROM acciones
            WHERE automatica = TRUE
            ORDER BY creado_en DESC
            LIMIT %s
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (limite,))
                return [dict(f) for f in cur.fetchall()]
        except psycopg2.Error as e:
            logger.error("Error obteniendo acciones: %s", e)
            return []

    def obtener_estadisticas(self) -> dict:
        """
        Estadísticas globales del agente: totales por tabla y últimas 24h.

        Returns:
            dict con conteos y resumen de actividad.
        """
        sql_totales = """
            SELECT
                (SELECT COUNT(*) FROM eventos) AS total_eventos,
                (SELECT COUNT(*) FROM acciones) AS total_acciones,
                (SELECT COUNT(*) FROM metricas) AS total_metricas,
                (SELECT COUNT(*) FROM eventos WHERE creado_en > NOW() - INTERVAL '24 hours') AS eventos_24h,
                (SELECT COUNT(*) FROM acciones WHERE creado_en > NOW() - INTERVAL '24 hours') AS acciones_24h
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql_totales)
                row = cur.fetchone()
                return dict(row) if row else {}
        except psycopg2.Error as e:
            logger.error("Error obteniendo estadísticas: %s", e)
            return {}

    # ─── Patrones de aprendizaje ──────────────────────────────

    def guardar_patron(self, nombre: str, descripcion: str, datos: dict) -> int:
        """
        Guarda o actualiza un patrón aprendido por el agente.

        Returns:
            ID del patrón.
        """
        sql_upsert = """
            INSERT INTO patrones (nombre, descripcion, datos, ocurrencias)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (nombre) DO UPDATE
                SET ocurrencias = patrones.ocurrencias + 1,
                    datos = EXCLUDED.datos,
                    actualizado_en = NOW()
            RETURNING id
        """
        # TODO: Agregar restricción UNIQUE en nombre si se necesita ON CONFLICT
        sql_insert = """
            INSERT INTO patrones (nombre, descripcion, datos)
            VALUES (%s, %s, %s)
            RETURNING id
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql_insert, (nombre, descripcion, json.dumps(datos)))
                return cur.fetchone()["id"]
        except psycopg2.Error as e:
            logger.error("Error guardando patrón: %s", e)
            return -1

    # ─── Usuarios y autenticación ─────────────────────────────

    def crear_usuario(
        self,
        usuario_id: str,
        email: str,
        username: str,
        password_hash: str,
        rol: str = "viewer",
        activo: bool = True,
    ) -> Optional[dict]:
        """
        Inserta un nuevo usuario.

        Args:
            usuario_id: UUID v5 generado a partir del email.
            email: Email único del usuario.
            username: Nombre de usuario único.
            password_hash: Hash bcrypt de la contraseña.
            rol: 'admin' | 'operator' | 'viewer'.
            activo: True si la cuenta está habilitada.

        Returns:
            dict con el usuario creado, o None si falló (e.g. email duplicado).
        """
        sql = """
            INSERT INTO usuarios (id, email, username, password_hash, rol, activo)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, email, username, rol, activo, creado_en
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (
                    usuario_id, email.strip().lower(), username.strip(),
                    password_hash, rol, activo,
                ))
                fila = cur.fetchone()
                logger.info("Usuario creado [%s] rol=%s", email, rol)
                return dict(fila) if fila else None
        except psycopg2.errors.UniqueViolation:
            logger.warning("Usuario duplicado: %s / %s", email, username)
            return None
        except psycopg2.Error as e:
            logger.error("Error creando usuario: %s", e)
            return None

    def obtener_usuario_por_email(self, email: str) -> Optional[dict]:
        """Busca un usuario por email (case-insensitive). Incluye password_hash."""
        sql = """
            SELECT id, email, username, password_hash, rol, activo,
                   ultimo_login, creado_en, actualizado_en
            FROM usuarios
            WHERE email = %s
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (email.strip().lower(),))
                fila = cur.fetchone()
                return dict(fila) if fila else None
        except psycopg2.Error as e:
            logger.error("Error buscando usuario por email: %s", e)
            return None

    def obtener_usuario_por_id(self, usuario_id: str) -> Optional[dict]:
        """Busca un usuario por su UUID. NO devuelve password_hash."""
        sql = """
            SELECT id, email, username, rol, activo,
                   ultimo_login, creado_en, actualizado_en
            FROM usuarios
            WHERE id = %s
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (usuario_id,))
                fila = cur.fetchone()
                return dict(fila) if fila else None
        except psycopg2.Error as e:
            logger.error("Error buscando usuario por id: %s", e)
            return None

    def listar_usuarios(self) -> list[dict]:
        """Lista todos los usuarios (sin password_hash)."""
        sql = """
            SELECT id, email, username, rol, activo,
                   ultimo_login, creado_en, actualizado_en
            FROM usuarios
            ORDER BY creado_en DESC
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql)
                return [dict(f) for f in cur.fetchall()]
        except psycopg2.Error as e:
            logger.error("Error listando usuarios: %s", e)
            return []

    def actualizar_usuario(
        self,
        usuario_id: str,
        username: Optional[str] = None,
        rol: Optional[str] = None,
        activo: Optional[bool] = None,
    ) -> Optional[dict]:
        """
        Actualiza campos editables de un usuario (no email — define el UUID v5).

        Returns:
            Usuario actualizado, o None si no existe / falló.
        """
        campos = []
        valores: list = []
        if username is not None:
            campos.append("username = %s"); valores.append(username.strip())
        if rol is not None:
            campos.append("rol = %s"); valores.append(rol)
        if activo is not None:
            campos.append("activo = %s"); valores.append(activo)
        if not campos:
            return self.obtener_usuario_por_id(usuario_id)

        campos.append("actualizado_en = NOW()")
        valores.append(usuario_id)

        sql = f"""
            UPDATE usuarios SET {', '.join(campos)}
            WHERE id = %s
            RETURNING id, email, username, rol, activo, ultimo_login, creado_en, actualizado_en
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, tuple(valores))
                fila = cur.fetchone()
                if fila:
                    logger.info("Usuario actualizado [%s]", usuario_id)
                return dict(fila) if fila else None
        except psycopg2.errors.UniqueViolation:
            logger.warning("Username duplicado al actualizar: %s", username)
            return None
        except psycopg2.Error as e:
            logger.error("Error actualizando usuario: %s", e)
            return None

    def cambiar_password(self, usuario_id: str, nuevo_hash: str) -> bool:
        """Cambia el hash de contraseña de un usuario."""
        sql = """
            UPDATE usuarios SET password_hash = %s, actualizado_en = NOW()
            WHERE id = %s
        """
        try:
            with self._cursor() as cur:
                cur.execute(sql, (nuevo_hash, usuario_id))
                actualizados = cur.rowcount
                if actualizados:
                    logger.info("Password cambiada para usuario [%s]", usuario_id)
                return actualizados > 0
        except psycopg2.Error as e:
            logger.error("Error cambiando password: %s", e)
            return False

    def registrar_login(self, usuario_id: str) -> None:
        """Marca la fecha del último login exitoso."""
        sql = "UPDATE usuarios SET ultimo_login = NOW() WHERE id = %s"
        try:
            with self._cursor() as cur:
                cur.execute(sql, (usuario_id,))
        except psycopg2.Error as e:
            logger.error("Error registrando login: %s", e)

    def eliminar_usuario(self, usuario_id: str) -> bool:
        """Elimina un usuario por UUID."""
        sql = "DELETE FROM usuarios WHERE id = %s"
        try:
            with self._cursor() as cur:
                cur.execute(sql, (usuario_id,))
                eliminados = cur.rowcount
                if eliminados:
                    logger.info("Usuario eliminado [%s]", usuario_id)
                return eliminados > 0
        except psycopg2.Error as e:
            logger.error("Error eliminando usuario: %s", e)
            return False

    # ─── Desconexión ──────────────────────────────────────────

    def desconectar(self) -> None:
        """Cierra la conexión con PostgreSQL."""
        if self._conexion and not self._conexion.closed:
            self._conexion.close()
            self._conexion = None
            logger.info("Conexión PostgreSQL cerrada")

    def __del__(self):
        self.desconectar()
