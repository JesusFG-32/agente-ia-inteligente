"""
agente.py
=========
Clase principal del Agente IA.
Usa Google Gemini para analizar métricas, detectar anomalías,
decidir acciones correctivas y responder preguntas en lenguaje natural.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

import google.generativeai as genai

import config
from adaptadores import BaseDatos, AdaptadorMongoDB

logger = logging.getLogger("agente-ia.agente")


class AgenteIA:
    """
    Agente inteligente basado en Google Gemini que monitorea infraestructura.

    Responsabilidades:
        - Analizar métricas de Nginx y MariaDB
        - Detectar anomalías usando IA
        - Decidir acciones correctivas
        - Responder preguntas en lenguaje natural
        - Persistir eventos y aprender patrones

    Uso:
        agente = AgenteIA()
        resultado = agente.analizar_metricas({"nginx": {...}, "mariadb": {...}})
    """

    # Prompt del sistema que define el comportamiento del agente
    SYSTEM_PROMPT = """
    Eres un agente experto en administración de sistemas Linux, Nginx y MariaDB.
    Tu rol es:
    1. Analizar métricas de rendimiento y detectar anomalías.
    2. Sugerir y ejecutar acciones correctivas cuando sea necesario.
    3. Responder preguntas técnicas de administración de sistemas.
    4. Aprender de los patrones observados para mejorar las predicciones.

    Cuando analices métricas, responde SIEMPRE en JSON con esta estructura:
    {
        "anomalias": [{"tipo": "...", "descripcion": "...", "severidad": "info|warning|error|critico"}],
        "recomendaciones": ["..."],
        "accion_inmediata": true|false,
        "accion_sugerida": "ninguna|reiniciar_nginx|matar_query|optimizar_bd|otro",
        "resumen": "..."
    }
    """

    def __init__(
        self,
        db: Optional[BaseDatos] = None,
        mongodb: Optional[AdaptadorMongoDB] = None,
    ) -> None:
        """
        Inicializa el agente y conecta a Google Gemini.

        Args:
            db: Instancia de BaseDatos para persistencia. Si no se provee,
                se crea una nueva con la configuración del entorno.
            mongodb: Instancia de AdaptadorMongoDB para persistir historiales de chat.
        """
        self._inicializar_gemini()
        self.db = db or self._crear_bd()
        self.mongodb = mongodb
        # Fallback en memoria estructurado por session_id
        self.historiales_memoria: dict[str, list[dict]] = {}
        # Historial legado para mantener compatibilidad
        self.historial_chat: list[dict] = []
        logger.info("AgenteIA inicializado con modelo '%s'", config.GEMINI_MODEL)

    def _inicializar_gemini(self) -> None:
        """Configura el SDK de Google Gemini."""
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY no está configurada en .env")
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.modelo = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=self.SYSTEM_PROMPT,
        )
        logger.info("Gemini configurado con modelo: %s", config.GEMINI_MODEL)

    def _crear_bd(self) -> Optional[BaseDatos]:
        """Crea la conexión a PostgreSQL desde configuración."""
        try:
            return BaseDatos(
                host=config.DB_HOST,
                port=config.DB_PORT,
                database=config.DB_NAME,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
            )
        except Exception as e:
            logger.warning("No se pudo conectar a PostgreSQL: %s (sin persistencia)", e)
            return None

    # ─── Análisis de métricas ─────────────────────────────────

    def analizar_metricas(self, metricas: dict) -> dict:
        """
        Envía las métricas a Gemini para análisis de anomalías.

        Args:
            metricas: dict con datos de Nginx, MariaDB u otras fuentes.

        Returns:
            dict con anomalías detectadas, recomendaciones y acción sugerida.
        """
        logger.info("Analizando métricas con Gemini...")
        prompt = f"""
        Analiza las siguientes métricas del sistema y detecta anomalías:

        ```json
        {json.dumps(metricas, indent=2, default=str)}
        ```

        Fecha/hora del análisis: {datetime.now().isoformat()}
        Responde únicamente con JSON válido según el formato indicado.
        """
        try:
            respuesta = self.modelo.generate_content(prompt)
            texto = respuesta.text.strip()
            # Limpiar bloques de código markdown si los hay
            if texto.startswith("```"):
                texto = texto.split("```")[1]
                if texto.startswith("json"):
                    texto = texto[4:]
            resultado = json.loads(texto)
            logger.info(
                "Análisis completado — %d anomalías detectadas",
                len(resultado.get("anomalias", [])),
            )
            # Persistir análisis
            if self.db:
                for anomalia in resultado.get("anomalias", []):
                    self.guardar_evento(
                        {"tipo": "anomalia", **anomalia, "metricas_origen": metricas},
                        self.db,
                    )
            return resultado
        except json.JSONDecodeError as e:
            logger.error("Respuesta de Gemini no es JSON válido: %s", e)
            return {
                "anomalias": [],
                "recomendaciones": ["Error al parsear respuesta de IA"],
                "accion_inmediata": False,
                "accion_sugerida": "ninguna",
                "resumen": f"Error de análisis: {e}",
            }
        except Exception as e:
            logger.error("Error en analizar_metricas: %s", e)
            return {
                "anomalias": [],
                "recomendaciones": [],
                "accion_inmediata": False,
                "accion_sugerida": "ninguna",
                "resumen": f"Error: {e}",
            }

    # ─── Decisión de acciones ─────────────────────────────────

    def decidir_accion(self, anomalia: dict) -> dict:
        """
        Dado un análisis de anomalía, decide la acción más apropiada.

        Args:
            anomalia: dict con la anomalía detectada (tipo, descripcion, severidad).

        Returns:
            dict con: accion (str), razon (str), parametros (dict), prioridad (str)
        """
        logger.info("Decidiendo acción para anomalía: %s", anomalia.get("tipo"))
        prompt = f"""
        Se detectó la siguiente anomalía en el sistema:
        {json.dumps(anomalia, indent=2, default=str)}

        Decide la mejor acción a tomar. Responde en JSON:
        {{
            "accion": "ninguna|reiniciar_nginx|matar_query|optimizar_bd|escalar_alerta|monitorear",
            "razon": "explicación breve",
            "parametros": {{}},
            "prioridad": "baja|media|alta|critica",
            "riesgo": "descripción del riesgo de la acción"
        }}
        """
        try:
            respuesta = self.modelo.generate_content(prompt)
            texto = respuesta.text.strip()
            if texto.startswith("```"):
                texto = texto.split("```")[1]
                if texto.startswith("json"):
                    texto = texto[4:]
            decision = json.loads(texto)
            logger.info("Acción decidida: %s (prioridad: %s)", decision.get("accion"), decision.get("prioridad"))
            return decision
        except Exception as e:
            logger.error("Error decidiendo acción: %s", e)
            return {
                "accion": "ninguna",
                "razon": f"Error al procesar: {e}",
                "parametros": {},
                "prioridad": "baja",
                "riesgo": "desconocido",
            }

    # ─── Chat inteligente ─────────────────────────────────────

    def responder_pregunta(self, pregunta: str, session_id: str = "default") -> str:
        """
        Responde una pregunta en lenguaje natural sobre el sistema, cargando y
        actualizando el historial desde MongoDB o memoria.

        Args:
            pregunta: Pregunta del usuario en texto libre.
            session_id: Identificador único de la sesión de chat.

        Returns:
            Respuesta en texto del agente.
        """
        logger.info("Respondiendo pregunta para sesión '%s': '%s'", session_id, pregunta[:80])

        # 1. Obtener historial previo (MongoDB o memoria)
        historial = []
        if self.mongodb and self.mongodb.activo:
            historial = self.mongodb.obtener_historial(session_id)
        else:
            historial = self.historiales_memoria.get(session_id, [])

        # 2. Agregar mensaje del usuario
        historial.append({"role": "user", "parts": [pregunta]})

        try:
            # start_chat espera el historial sin el mensaje actual, y luego se envía
            chat = self.modelo.start_chat(history=historial[:-1])
            respuesta = chat.send_message(pregunta)
            texto_respuesta = respuesta.text

            # 3. Agregar respuesta del modelo
            historial.append({"role": "model", "parts": [texto_respuesta]})

            # 4. Truncar si supera el tamaño de ventana de contexto (40 mensajes / 20 interacciones)
            if len(historial) > 40:
                historial = historial[-40:]

            # 5. Persistir historial actualizado
            if self.mongodb and self.mongodb.activo:
                self.mongodb.guardar_historial(session_id, historial)
            else:
                self.historiales_memoria[session_id] = historial
                # Mantener compatibilidad con el atributo legado para pruebas unitarias de sesión única
                if session_id == "default":
                    self.historial_chat = historial

            return texto_respuesta
        except Exception as e:
            logger.error("Error respondiendo pregunta para sesión %s: %s", session_id, e)
            return f"Lo siento, ocurrió un error al procesar tu pregunta: {e}"

    # ─── Persistencia ─────────────────────────────────────────

    def guardar_evento(self, evento: dict, db: Optional[BaseDatos] = None) -> int:
        """
        Persiste un evento en PostgreSQL.

        Args:
            evento: dict con los datos del evento.
            db: Instancia de BaseDatos (usa self.db si no se provee).

        Returns:
            ID del evento guardado, o -1 si falló.
        """
        base = db or self.db
        if not base:
            logger.warning("Sin BD disponible — evento no persistido")
            return -1
        return base.guardar_evento(
            tipo=evento.get("tipo", "desconocido"),
            descripcion=evento.get("descripcion", ""),
            severidad=evento.get("severidad", "info"),
            datos=evento,
        )

    # ─── Aprendizaje ──────────────────────────────────────────

    def aprender_patron(self, patron: dict) -> dict:
        """
        Analiza y guarda un patrón de comportamiento para aprendizaje futuro.

        Args:
            patron: dict describiendo el patrón observado.

        Returns:
            dict con: guardado (bool), nombre_patron (str), id (int)
        """
        logger.info("Aprendiendo nuevo patrón...")
        prompt = f"""
        El sistema observó el siguiente patrón de comportamiento:
        {json.dumps(patron, indent=2, default=str)}

        Genera un nombre descriptivo y una descripción concisa para este patrón.
        Responde en JSON:
        {{
            "nombre": "nombre_corto_del_patron",
            "descripcion": "descripción legible",
            "relevancia": "alta|media|baja"
        }}
        """
        try:
            respuesta = self.modelo.generate_content(prompt)
            texto = respuesta.text.strip()
            if texto.startswith("```"):
                texto = texto.split("```")[1]
                if texto.startswith("json"):
                    texto = texto[4:]
            meta = json.loads(texto)
            patron_id = -1
            if self.db:
                patron_id = self.db.guardar_patron(
                    nombre=meta.get("nombre", "patron_desconocido"),
                    descripcion=meta.get("descripcion", ""),
                    datos=patron,
                )
            logger.info("Patrón aprendido: '%s' (id=%s)", meta.get("nombre"), patron_id)
            return {"guardado": True, "nombre_patron": meta.get("nombre"), "id": patron_id}
        except Exception as e:
            logger.error("Error aprendiendo patrón: %s", e)
            return {"guardado": False, "nombre_patron": None, "id": -1}

    def limpiar_historial(self, session_id: str = "default") -> None:
        """Resetea el historial del chat para una sesión."""
        if self.mongodb and self.mongodb.activo:
            self.mongodb.guardar_historial(session_id, [])
        else:
            self.historiales_memoria[session_id] = []
        if session_id == "default":
            self.historial_chat = []
        logger.info("Historial de chat para sesión '%s' limpiado", session_id)
