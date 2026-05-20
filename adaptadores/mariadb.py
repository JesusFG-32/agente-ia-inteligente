"""
adaptadores/mariadb.py
======================
Adaptador para monitorear MariaDB directamente via pymysql.
Proporciona métricas de rendimiento, queries, conexiones y acciones.
"""

import logging
from typing import Any, Optional

import pymysql
import pymysql.cursors

logger = logging.getLogger("agente-ia.mariadb")


class AdaptadorMariaDB:
    """
    Se conecta a MariaDB y expone métricas de rendimiento y salud.

    Uso:
        db = AdaptadorMariaDB(host="10.0.0.1", user="monitor", password="xxx")
        metricas = db.obtener_metricas()
        db.desconectar()
    """

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        port: int = 3306,
        connect_timeout: int = 10,
    ) -> None:
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.connect_timeout = connect_timeout
        self._conexion: Optional[pymysql.Connection] = None
        self._conectar()

    # ─── Conexión ─────────────────────────────────────────────

    def _conectar(self) -> None:
        """Establece la conexión con MariaDB."""
        try:
            self._conexion = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                port=self.port,
                connect_timeout=self.connect_timeout,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
            logger.info("Conectado a MariaDB en %s:%s", self.host, self.port)
        except pymysql.Error as e:
            logger.error("Error conectando a MariaDB: %s", e)
            raise

    def _reconectar_si_necesario(self) -> None:
        """Reconecta si la conexión se cerró."""
        if self._conexion is None or not self._conexion.open:
            logger.warning("MariaDB desconectado, reconectando...")
            self._conectar()

    # ─── Ejecución de queries ─────────────────────────────────

    def ejecutar_query(self, sql: str, args: tuple = ()) -> list[dict]:
        """
        Ejecuta una consulta SQL y retorna los resultados.

        Args:
            sql: Sentencia SQL a ejecutar.
            args: Parámetros para la consulta parametrizada.

        Returns:
            Lista de diccionarios con los resultados.
        """
        self._reconectar_si_necesario()
        try:
            with self._conexion.cursor() as cursor:
                cursor.execute(sql, args)
                return cursor.fetchall()
        except pymysql.Error as e:
            logger.error("Error ejecutando query '%s': %s", sql[:80], e)
            return []

    # ─── Métodos de monitoreo ─────────────────────────────────

    def obtener_estado_general(self) -> dict:
        """
        Obtiene variables de estado globales de MariaDB (SHOW STATUS).

        Returns:
            dict con las variables más relevantes de salud.
        """
        filas = self.ejecutar_query("SHOW GLOBAL STATUS")
        estado = {f["Variable_name"]: f["Value"] for f in filas}
        claves_relevantes = [
            "Uptime", "Threads_connected", "Threads_running",
            "Questions", "Slow_queries", "Aborted_clients",
            "Aborted_connects", "Bytes_received", "Bytes_sent",
            "Com_select", "Com_insert", "Com_update", "Com_delete",
            "Innodb_buffer_pool_reads", "Innodb_buffer_pool_read_requests",
        ]
        resumen = {k: estado.get(k, "N/A") for k in claves_relevantes}
        logger.debug("Estado MariaDB obtenido: %d vars", len(estado))
        return resumen

    def obtener_conexiones(self) -> dict:
        """
        Lista conexiones activas via SHOW PROCESSLIST.

        Returns:
            dict con: total (int), lista (list[dict])
        """
        filas = self.ejecutar_query("SHOW FULL PROCESSLIST")
        logger.info("Conexiones activas MariaDB: %d", len(filas))
        return {"total": len(filas), "lista": filas}

    def obtener_uso_recursos(self) -> dict:
        """
        Obtiene el tamaño de tablas por base de datos.

        Returns:
            dict con: bases_de_datos (list[dict]) con nombre y tamaño MB.
        """
        sql = """
            SELECT
                table_schema AS base_datos,
                ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS tamano_mb
            FROM information_schema.TABLES
            GROUP BY table_schema
            ORDER BY tamano_mb DESC
        """
        filas = self.ejecutar_query(sql)
        logger.debug("Uso de recursos MariaDB calculado")
        return {"bases_de_datos": filas}

    def obtener_queries_lentas(self, umbral_segundos: int = 5) -> dict:
        """
        Obtiene queries que llevan más de N segundos ejecutándose.

        Args:
            umbral_segundos: Tiempo mínimo (en segundos) para considerar lenta.

        Returns:
            dict con: total (int), queries (list[dict])
        """
        filas = self.ejecutar_query("SHOW FULL PROCESSLIST")
        lentas = [
            f for f in filas
            if f.get("Time") is not None and int(f.get("Time", 0)) >= umbral_segundos
            and f.get("Command") == "Query"
        ]
        logger.info("Queries lentas (>%ds): %d", umbral_segundos, len(lentas))
        return {"total": len(lentas), "queries": lentas}

    def obtener_metricas(self) -> dict:
        """
        Recopila todas las métricas disponibles de MariaDB.

        Returns:
            dict completo con estado, conexiones, recursos y queries lentas.
        """
        logger.info("Recopilando métricas completas de MariaDB...")
        try:
            return {
                "origen": "mariadb",
                "estado_general": self.obtener_estado_general(),
                "conexiones": self.obtener_conexiones(),
                "uso_recursos": self.obtener_uso_recursos(),
                "queries_lentas": self.obtener_queries_lentas(),
                "ok": True,
            }
        except Exception as e:
            logger.error("Error obteniendo métricas MariaDB: %s", e)
            return {"origen": "mariadb", "ok": False, "error": str(e)}

    # ─── Acciones ─────────────────────────────────────────────

    def matar_query(self, proceso_id: int) -> dict:
        """
        Mata una query por su ID de proceso (KILL QUERY).

        Args:
            proceso_id: ID del proceso a terminar.

        Returns:
            dict con: exito (bool), mensaje (str)
        """
        logger.warning("Matando query con ID=%s", proceso_id)
        try:
            self.ejecutar_query(f"KILL QUERY {int(proceso_id)}")
            return {"exito": True, "mensaje": f"Query {proceso_id} terminada"}
        except Exception as e:
            logger.error("Error matando query %s: %s", proceso_id, e)
            return {"exito": False, "mensaje": str(e)}

    def optimizar_tablas(self, base_datos: str) -> dict:
        """
        Ejecuta OPTIMIZE TABLE en todas las tablas de una base de datos.

        Args:
            base_datos: Nombre de la base de datos a optimizar.

        Returns:
            dict con: exito (bool), tablas_optimizadas (list), mensaje (str)
        """
        logger.info("Optimizando tablas de base de datos: %s", base_datos)
        try:
            tablas = self.ejecutar_query(
                "SELECT table_name FROM information_schema.TABLES WHERE table_schema = %s",
                (base_datos,),
            )
            optimizadas = []
            for t in tablas:
                nombre = t["table_name"]
                self.ejecutar_query(f"OPTIMIZE TABLE `{base_datos}`.`{nombre}`")
                optimizadas.append(nombre)
                logger.debug("Tabla optimizada: %s", nombre)
            return {
                "exito": True,
                "tablas_optimizadas": optimizadas,
                "mensaje": f"{len(optimizadas)} tablas optimizadas en '{base_datos}'",
            }
        except Exception as e:
            logger.error("Error optimizando tablas de %s: %s", base_datos, e)
            return {"exito": False, "tablas_optimizadas": [], "mensaje": str(e)}

    # ─── Desconexión ──────────────────────────────────────────

    def desconectar(self) -> None:
        """Cierra la conexión con MariaDB."""
        if self._conexion and self._conexion.open:
            self._conexion.close()
            self._conexion = None
            logger.info("Conexión MariaDB cerrada")

    def __del__(self):
        self.desconectar()
