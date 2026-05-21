"""
adaptadores/mongodb.py
======================
Adaptador para persistir el contexto histórico de los chats en MongoDB.
Gestiona la carga y actualización del historial de conversaciones por sesión.
"""

import logging
from datetime import datetime
from typing import Any, Optional
import pymongo
from pymongo.errors import PyMongoError

logger = logging.getLogger("agente-ia.mongodb")


class AdaptadorMongoDB:
    """
    Gestiona la conexión y persistencia de historiales de conversación en MongoDB.

    Uso:
        mongo = AdaptadorMongoDB(uri="mongodb://localhost:27017/", db_name="agente_ia", collection_name="conversaciones")
        historial = mongo.obtener_historial("mi-sesion-123")
        mongo.guardar_historial("mi-sesion-123", [{"role": "user", "parts": ["hola"]}])
        mongo.desconectar()
    """

    def __init__(
        self,
        uri: str,
        db_name: str,
        collection_name: str,
        timeout_ms: int = 2000,
    ) -> None:
        self.uri = uri
        self.db_name = db_name
        self.collection_name = collection_name
        self.timeout_ms = timeout_ms
        self._cliente: Optional[pymongo.MongoClient] = None
        self._db: Optional[pymongo.database.Database] = None
        self._collection: Optional[pymongo.collection.Collection] = None
        self._conectar()

    def _conectar(self) -> None:
        """Establece la conexión con MongoDB y verifica salud (ping)."""
        try:
            # Crear cliente con timeout rápido para no bloquear el inicio si está caído
            self._cliente = pymongo.MongoClient(
                self.uri,
                serverSelectionTimeoutMS=self.timeout_ms,
            )
            # Forzar verificación de conexión
            self._cliente.admin.command("ping")
            self._db = self._cliente[self.db_name]
            self._collection = self._db[self.collection_name]
            
            # Crear índice en session_id para búsquedas ultra rápidas
            self._collection.create_index("session_id", unique=True)
            
            logger.info(
                "Conectado a MongoDB en '%s', DB: '%s', Colección: '%s'",
                self.uri.split("@")[-1],  # Ocultar credenciales en el log
                self.db_name,
                self.collection_name,
            )
        except PyMongoError as e:
            logger.warning(
                "No se pudo conectar a MongoDB: %s. El agente usará fallback en memoria.",
                e,
            )
            self._cliente = None
            self._db = None
            self._collection = None

    @property
    def activo(self) -> bool:
        """Verifica si la conexión con MongoDB está activa y lista."""
        if self._cliente is None or self._collection is None:
            return False
        try:
            self._cliente.admin.command("ping")
            return True
        except PyMongoError:
            return False

    def obtener_historial(self, session_id: str) -> list[dict]:
        """
        Recupera el historial de chat de una sesión específica.

        Args:
            session_id: Identificador único de la conversación.

        Returns:
            Lista de mensajes de chat en formato dict (Gemini format).
        """
        if not self.activo:
            logger.debug("MongoDB inactivo. No se puede obtener historial para: %s", session_id)
            return []

        try:
            doc = self._collection.find_one({"session_id": session_id})
            if doc and "historial" in doc:
                logger.info("Historial recuperado desde MongoDB para sesión: %s", session_id)
                return doc["historial"]
            logger.info("No se encontró historial en MongoDB para sesión: %s (se creará una nueva)", session_id)
            return []
        except PyMongoError as e:
            logger.error("Error al obtener historial de MongoDB para %s: %s", session_id, e)
            return []

    def guardar_historial(self, session_id: str, historial: list[dict]) -> bool:
        """
        Guarda o actualiza el historial de chat de una sesión.

        Args:
            session_id: Identificador único de la conversación.
            historial: Lista completa de mensajes del chat a persistir.

        Returns:
            True si se guardó con éxito, False de lo contrario.
        """
        if not self.activo:
            logger.warning("MongoDB inactivo. No se pudo guardar historial para: %s", session_id)
            return False

        try:
            self._collection.update_one(
                {"session_id": session_id},
                {
                    "$set": {
                        "historial": historial,
                        "actualizado_en": datetime.utcnow(),
                    }
                },
                upsert=True,
            )
            logger.info("Historial guardado/actualizado en MongoDB para sesión: %s", session_id)
            return True
        except PyMongoError as e:
            logger.error("Error al guardar historial en MongoDB para %s: %s", session_id, e)
            return False

    def desconectar(self) -> None:
        """Cierra de forma limpia la conexión con MongoDB."""
        if self._cliente:
            self._cliente.close()
            self._cliente = None
            self._db = None
            self._collection = None
            logger.info("Conexión MongoDB cerrada de forma limpia")

    def __del__(self):
        self.desconectar()
