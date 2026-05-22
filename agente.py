import os
import json
import logging
from datetime import datetime
from typing import Optional

import google.generativeai as genai
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
import psycopg2
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=os.getenv("AGENT_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("agente_ia")

PROMPT_ANALISIS = """
Eres un experto en monitoreo de infraestructura.
Analiza las siguientes métricas y detecta anomalías:

Métricas:
{metricas}

Detecta:
1. CPU alta (>80%)
2. Memoria baja (<20%)
3. Conexiones excesivas (>150)
4. Queries lentas (>5 segundos)
5. Procesos problemáticos

Devuelve SOLO JSON (sin markdown):
{{
    "anomalias": [
        {{"tipo": "...", "severidad": "CRÍTICA/ALTA/MEDIA/BAJA", "descripcion": "...", "valor": ...}}
    ],
    "estado_general": "CRÍTICO/ALERTA/NORMAL",
    "resumen": "...",
    "acciones_sugeridas": [
        {{"accion": "...", "justificacion": "..."}}
    ]
}}
"""

PROMPT_RESPUESTA = """
Eres un asistente experto en infraestructura y sistemas.
Tienes acceso a histórico de conversaciones anteriores.

Histórico previo:
{contexto_historico}

Pregunta del usuario: {pregunta}

Responde de forma:
- Concisa y útil
- Considerando conversaciones previas
- Como un experto
- En español
- Sin repetir información que ya diste antes
"""

PROMPT_DECISION = """
Eres un agente autónomo de infraestructura.
Una anomalía ha sido detectada:

{anomalia}

Decide qué acción tomar considerando:
- Riesgo de ejecutarla
- Impacto en el sistema
- Necesidad de confirmación humana

Responde SOLO en JSON:
{{
    "accion": "nombre_accion",
    "parametros": {{}},
    "ejecutar_automaticamente": true,
    "razon": "...",
    "rollback_plan": "..."
}}
"""

class AgenteIA:
    """
    Agente de Inteligencia Artificial para monitoreo y administración de infraestructura.
    
    Analiza métricas de sistemas, detecta anomalías usando IA, mantiene un
    contexto histórico y aprende patrones para mejorar su capacidad de 
    respuesta y toma de decisiones.
    """

    def __init__(self, gemini_api_key: str, mongodb_uri: str, postgres_connection: dict) -> None:
        """
        Inicializa el Agente IA estableciendo las conexiones necesarias.
        
        Args:
            gemini_api_key: API Key de Google Generative AI (Gemini).
            mongodb_uri: URI de conexión a MongoDB.
            postgres_connection: Diccionario con credenciales para PostgreSQL 
                                 (host, port, dbname, user, password).
        """
        self.gemini_api_key = gemini_api_key
        self.mongodb_uri = mongodb_uri
        self.postgres_connection = postgres_connection
        
        self.mongo_client = None
        self.db_mongo = None
        self.pg_conn = None
        self.modelo = None
        
        self._conectar_gemini()
        self._conectar_mongodb()
        self._conectar_postgresql()

    def _conectar_gemini(self) -> None:
        """Configura la API de Gemini, valida la key e inicializa el modelo."""
        try:
            if not self.gemini_api_key:
                raise ValueError("GEMINI_API_KEY no proporcionada.")
            genai.configure(api_key=self.gemini_api_key)
            # Inicializamos con gemini-1.5-pro o gemini-pro dependiendo de disponibilidad
            self.modelo = genai.GenerativeModel('gemini-1.5-pro-latest')
            logger.info("Conexión exitosa a Gemini API.")
        except Exception as e:
            logger.error(f"Fallo al conectar con Gemini: {e}")

    def _conectar_mongodb(self) -> None:
        """Intenta conectar a MongoDB y prepara las colecciones necesarias."""
        try:
            if not self.mongodb_uri:
                logger.warning("MONGODB_URI no configurado. Se deshabilitará el historial.")
                return
            
            self.mongo_client = MongoClient(self.mongodb_uri, serverSelectionTimeoutMS=5000)
            self.mongo_client.admin.command('ping')
            
            # Asumimos una base de datos por defecto si no se especifica en la URI
            db_name = self.mongodb_uri.split('/')[-1] if '/' in self.mongodb_uri.split('mongodb://')[-1] else 'agente_ia'
            if '?' in db_name:
                db_name = db_name.split('?')[0]
                
            self.db_mongo = self.mongo_client[db_name]
            
            # Crear collections si no existen de forma implícita (MongoDB lo hace al insertar)
            logger.info("Conexión exitosa a MongoDB.")
        except ConnectionFailure as e:
            logger.warning(f"No se pudo conectar a MongoDB. Se continuará sin persistencia de historial: {e}")
            self.mongo_client = None
            self.db_mongo = None
        except Exception as e:
            logger.error(f"Error inesperado al conectar a MongoDB: {e}")
            self.mongo_client = None
            self.db_mongo = None

    def _conectar_postgresql(self) -> None:
        """Intenta conectar a PostgreSQL para persistencia de eventos y acciones."""
        try:
            self.pg_conn = psycopg2.connect(**self.postgres_connection)
            logger.info("Conexión exitosa a PostgreSQL.")
        except Exception as e:
            logger.error(f"Fallo crítico al conectar con PostgreSQL: {e}")
            # Consideramos notificar a un admin de ser necesario, pero por ahora solo log
            self.pg_conn = None

    def desconectar(self) -> None:
        """Cierra todas las conexiones establecidas (MongoDB y PostgreSQL)."""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("Conexión a MongoDB cerrada.")
            
        if self.pg_conn:
            self.pg_conn.close()
            logger.info("Conexión a PostgreSQL cerrada.")

    def _limpiar_respuesta_json(self, texto: str) -> dict:
        """
        Helper para limpiar y parsear respuestas JSON desde Gemini.
        
        Args:
            texto: Texto en crudo devuelto por Gemini.
            
        Returns:
            dict: Objeto JSON parseado o un dict vacío en caso de error.
        """
        if not texto:
            return {}
            
        texto_limpio = texto.strip()
        if texto_limpio.startswith("```"):
            lineas = texto_limpio.split("\n")
            if lineas and lineas[0].startswith("```"):
                lineas = lineas[1:]
            if lineas and lineas[-1].startswith("```"):
                lineas = lineas[:-1]
            texto_limpio = "\n".join(lineas).strip()
            
        try:
            return json.loads(texto_limpio)
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON desde respuesta de Gemini: {e}\nTexto original: {texto}")
            # Intentar reparar el JSON de manera básica no es trivial, devolvemos fallback
            return {}

    def _guardar_en_mongodb(self, collection_name: str, documento: dict) -> bool:
        """Helper para guardar un documento en una colección específica de MongoDB."""
        if not self.db_mongo:
            return False
        try:
            self.db_mongo[collection_name].insert_one(documento)
            return True
        except Exception as e:
            logger.error(f"Error guardando en MongoDB collection {collection_name}: {e}")
            return False

    def _consultar_mongodb(self, collection_name: str, query: dict, limite: int) -> list:
        """Helper para consultar documentos de una colección de MongoDB."""
        if not self.db_mongo:
            return []
        try:
            cursor = self.db_mongo[collection_name].find(query).sort("timestamp", -1).limit(limite)
            return list(cursor)
        except Exception as e:
            logger.error(f"Error consultando MongoDB collection {collection_name}: {e}")
            return []

    def _obtener_contexto_chat(self, limite: int = 10) -> list:
        """Obtiene el historial de chat de MongoDB para contexto."""
        documentos = self._consultar_mongodb("chat_history", {}, limite)
        # Invertimos para que el orden sea cronológico (más viejo a más nuevo)
        return list(reversed(documentos))

    def _clasificar_severidad(self, tipo_anomalia: str, valor: float) -> str:
        """Clasifica automáticamente la severidad de una anomalía con reglas estáticas."""
        # Esta es una implementación básica local
        tipo = tipo_anomalia.lower()
        if "cpu" in tipo:
            if valor > 95: return "CRÍTICA"
            if valor > 85: return "ALTA"
            if valor > 70: return "MEDIA"
        elif "memoria" in tipo:
            if valor < 5: return "CRÍTICA"
            if valor < 15: return "ALTA"
            if valor < 30: return "MEDIA"
        elif "conexion" in tipo:
            if valor > 500: return "CRÍTICA"
            if valor > 200: return "ALTA"
            if valor > 100: return "MEDIA"
            
        return "BAJA"

    def _detectar_anomalias_en_metricas(self, metricas: dict) -> list:
        """Analiza métricas localmente usando reglas heurísticas antes de Gemini."""
        anomalias = []
        # Analizar Nginx
        nginx = metricas.get("nginx", {})
        conexiones = nginx.get("active_connections", 0)
        if conexiones > 150:
            anomalias.append({
                "tipo": "conexiones_altas_nginx",
                "severidad": self._clasificar_severidad("conexiones", conexiones),
                "descripcion": f"Conexiones activas en Nginx son altas ({conexiones}).",
                "valor": conexiones
            })
            
        # Analizar MariaDB/PostgreSQL (queries)
        mariadb = metricas.get("mariadb", {})
        slow_queries = mariadb.get("slow_queries", 0)
        if slow_queries > 5:
            anomalias.append({
                "tipo": "queries_lentas",
                "severidad": "ALTA" if slow_queries > 20 else "MEDIA",
                "descripcion": f"Se detectaron {slow_queries} queries lentas en la base de datos.",
                "valor": slow_queries
            })
            
        # Analizar CPU general si existe
        sistema = metricas.get("sistema", {})
        cpu = sistema.get("cpu_usage", 0)
        if cpu > 80:
             anomalias.append({
                "tipo": "cpu_alta",
                "severidad": self._clasificar_severidad("cpu", cpu),
                "descripcion": f"Uso de CPU del sistema elevado al {cpu}%.",
                "valor": cpu
            })
            
        return anomalias

    def generar_prompt_analisis(self, metricas: dict) -> str:
        """Genera el prompt dinámico para análisis de métricas por Gemini."""
        metricas_str = json.dumps(metricas, indent=2)
        return PROMPT_ANALISIS.format(metricas=metricas_str)

    def generar_prompt_respuesta(self, pregunta: str, contexto: list) -> str:
        """Genera el prompt para responder preguntas considerando el contexto histórico."""
        contexto_str = ""
        for msg in contexto:
            contexto_str += f"Usuario: {msg.get('usuario_pregunta', '')}\n"
            contexto_str += f"Agente: {msg.get('respuesta_agente', '')}\n\n"
            
        if not contexto_str:
            contexto_str = "No hay contexto previo."
            
        return PROMPT_RESPUESTA.format(contexto_historico=contexto_str, pregunta=pregunta)

    def analizar_metricas(self, metricas: dict) -> dict:
        """
        Recibe métricas del sistema, las analiza con heurística local y luego con Gemini.
        
        Args:
            metricas: Diccionario con métricas (ej. nginx, mariadb).
            
        Returns:
            Dict con las anomalías detectadas y el estado general.
        """
        logger.info("Iniciando análisis de métricas.")
        resultado_defecto = {
            "anomalias": [],
            "estado_general": "NORMAL",
            "resumen": "No se pudo completar el análisis mediante IA."
        }
        
        # 1. Detección local temprana
        anomalias_locales = self._detectar_anomalias_en_metricas(metricas)
        if anomalias_locales:
            logger.info(f"Anomalías locales detectadas preliminarmente: {len(anomalias_locales)}")

        # 2. Análisis avanzado con Gemini
        if not self.modelo:
            logger.warning("Modelo Gemini no inicializado. Se retorna análisis local básico.")
            resultado_defecto["anomalias"] = anomalias_locales
            if anomalias_locales:
                resultado_defecto["estado_general"] = "ALERTA"
                resultado_defecto["resumen"] = "Anomalías detectadas localmente."
            return resultado_defecto

        prompt = self.generar_prompt_analisis(metricas)
        try:
            logger.debug(f"Prompt enviado a Gemini para análisis: {prompt}")
            respuesta = self.modelo.generate_content(prompt)
            resultado = self._limpiar_respuesta_json(respuesta.text)
            
            if not resultado:
                # Fallback al local si JSON falla
                raise ValueError("JSON vacío o malformado retornado por Gemini.")
                
            # Combinar local con lo de Gemini (opcional, o confiar en Gemini)
            # Asumimos que Gemini provee la estructura correcta.
            
            # 3. Guardar en PostgreSQL (Eventos)
            if self.pg_conn:
                for anomalia in resultado.get("anomalias", []):
                    self.guardar_evento(
                        tipo="anomalia_detectada",
                        descripcion=anomalia.get("descripcion", "Sin descripción"),
                        severidad=anomalia.get("severidad", "BAJA"),
                        datos=anomalia
                    )
            
            logger.info("Análisis de métricas completado exitosamente con IA.")
            return resultado
            
        except Exception as e:
            logger.error(f"Error durante el análisis con Gemini: {e}")
            return resultado_defecto

    def generar_respuesta(self, pregunta: str, contexto_historico: list = None) -> str:
        """
        Genera una respuesta coherente usando el historial de chat.
        
        Args:
            pregunta: La pregunta del usuario.
            contexto_historico: Contexto explícito opcional (si no, lo busca de MongoDB).
            
        Returns:
            La respuesta en string.
        """
        if contexto_historico is None:
            contexto_historico = self._obtener_contexto_chat(limite=10)
            
        if not self.modelo:
            return "Lo siento, el modelo de IA no está disponible en este momento."
            
        prompt = self.generar_prompt_respuesta(pregunta, contexto_historico)
        try:
            logger.debug(f"Enviando pregunta a Gemini: {pregunta}")
            respuesta = self.modelo.generate_content(prompt)
            return respuesta.text.strip()
        except Exception as e:
            logger.error(f"Fallo al generar respuesta de chat: {e}")
            return "Ocurrió un error al procesar tu pregunta. Por favor, intenta de nuevo."

    def guardar_contexto_chat(self, usuario_pregunta: str, respuesta_agente: str, metadata: dict) -> bool:
        """
        Guarda la interacción del chat en MongoDB.
        
        Args:
            usuario_pregunta: Texto ingresado por el usuario.
            respuesta_agente: Texto generado por el agente.
            metadata: Datos extra como metricas_actuales, usuario_id, etc.
            
        Returns:
            bool: True si se guardó correctamente, False de lo contrario.
        """
        documento = {
            "timestamp": datetime.utcnow(),
            "usuario_pregunta": usuario_pregunta,
            "respuesta_agente": respuesta_agente,
            "metadata": metadata
        }
        return self._guardar_en_mongodb("chat_history", documento)

    def obtener_memoria(self, tipo: str, limite: int = 10) -> list:
        """
        Recupera memoria del agente desde MongoDB.
        
        Args:
            tipo: "chat_history", "patrones" o "anomalias_frecuentes".
            limite: Cantidad máxima de registros a retornar.
            
        Returns:
            Lista de documentos filtrados por contexto.
        """
        if tipo == "chat_history":
            return self._consultar_mongodb("chat_history", {}, limite)
        elif tipo == "patrones":
            return self._consultar_mongodb("patrones", {}, limite)
        elif tipo == "anomalias_frecuentes":
             # Asumimos que podemos agregar una estructura para anomalías frecuentes
             return self._consultar_mongodb("anomalias", {}, limite)
        else:
             logger.warning(f"Tipo de memoria no reconocido: {tipo}")
             return []

    def aprender_patron(self, patron_tipo: str, datos: dict) -> bool:
        """
        Analiza patrones detectados y los guarda para conocimiento futuro.
        
        Args:
            patron_tipo: Clasificación del patrón.
            datos: Detalles técnicos del patrón.
            
        Returns:
            bool: True si se aprendió exitosamente.
        """
        documento = {
            "timestamp": datetime.utcnow(),
            "tipo_patron": patron_tipo,
            "descripcion": f"Patrón de {patron_tipo} detectado en el sistema",
            "datos": datos,
            "confianza": 0.85, # Ejemplo
            "frecuencia": 1
        }
        exito = self._guardar_en_mongodb("patrones", documento)
        if exito:
            logger.info(f"Patrón aprendido y guardado: {patron_tipo}")
        return exito

    def decidir_accion(self, anomalia: dict) -> dict:
        """
        Solicita a Gemini decidir una acción para una anomalía específica.
        
        Args:
            anomalia: Diccionario con los detalles de la anomalía.
            
        Returns:
            Dict con los detalles de la decisión a ejecutar.
        """
        decision_defecto = {
            "accion": "ninguna",
            "parametros": {},
            "ejecutar_automaticamente": False,
            "razon": "Error al procesar la decisión",
            "rollback_plan": "N/A"
        }
        
        if not self.modelo:
            return decision_defecto
            
        anomalia_str = json.dumps(anomalia, indent=2)
        prompt = PROMPT_DECISION.format(anomalia=anomalia_str)
        
        try:
            logger.info(f"Solicitando decisión para anomalía de tipo: {anomalia.get('tipo', 'desconocido')}")
            respuesta = self.modelo.generate_content(prompt)
            decision = self._limpiar_respuesta_json(respuesta.text)
            
            if not decision:
                 raise ValueError("Respuesta JSON vacía en decisión.")
                 
            # Guardar decisión en PostgreSQL (Eventos/Acciones)
            if self.pg_conn:
                self.guardar_evento(
                    tipo="decision_autonoma",
                    descripcion=f"Acción decidida: {decision.get('accion')}",
                    severidad="INFO",
                    datos=decision
                )
                 
            return decision
        except Exception as e:
            logger.error(f"Fallo al decidir acción: {e}")
            return decision_defecto

    def guardar_evento(self, tipo: str, descripcion: str, severidad: str, datos: dict) -> int:
        """
        Guarda un evento persistente en PostgreSQL.
        
        Args:
            tipo: Categoría del evento.
            descripcion: Texto legible.
            severidad: "INFO", "WARNING", "ERROR", "CRÍTICA"
            datos: Objeto JSON con detalles.
            
        Returns:
            int: ID del evento guardado, o -1 en caso de error.
        """
        if not self.pg_conn:
            logger.warning("No se puede guardar evento, no hay conexión a PostgreSQL.")
            return -1
            
        try:
            cursor = self.pg_conn.cursor()
            
            # Asegurarse de que la tabla existe (o asumir que ya fue creada por migraciones)
            # Create table query omitido aquí, pero asumimos esquema:
            # id SERIAL PRIMARY KEY, tipo VARCHAR, descripcion TEXT, severidad VARCHAR, datos JSONB, fecha TIMESTAMP
            
            query = """
                INSERT INTO eventos (tipo, descripcion, severidad, datos, fecha)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id;
            """
            
            cursor.execute(query, (tipo, descripcion, severidad, json.dumps(datos), datetime.utcnow()))
            evento_id = cursor.fetchone()[0]
            self.pg_conn.commit()
            cursor.close()
            return evento_id
        except Exception as e:
            if self.pg_conn:
                self.pg_conn.rollback()
            logger.error(f"Error al guardar evento en PostgreSQL: {e}")
            return -1

    def obtener_estadisticas(self) -> dict:
        """
        Consulta y devuelve estadísticas de uso de eventos.
        
        Returns:
            dict con contadores.
        """
        stats = {
            "eventos_criticos": 0,
            "acciones_automaticas": 0,
            "patrones": 0
        }
        
        # Consultar MongoDB para patrones
        if self.db_mongo:
            try:
                stats["patrones"] = self.db_mongo["patrones"].count_documents({})
            except Exception as e:
                 logger.error(f"Error al contar patrones: {e}")
                 
        # Consultar PostgreSQL para eventos
        if self.pg_conn:
            try:
                cursor = self.pg_conn.cursor()
                cursor.execute("SELECT count(*) FROM eventos WHERE severidad IN ('CRÍTICA', 'ALTA')")
                stats["eventos_criticos"] = cursor.fetchone()[0]
                
                cursor.execute("SELECT count(*) FROM eventos WHERE tipo = 'decision_autonoma'")
                stats["acciones_automaticas"] = cursor.fetchone()[0]
                cursor.close()
            except Exception as e:
                if self.pg_conn:
                     self.pg_conn.rollback()
                logger.error(f"Error al consultar estadísticas en PostgreSQL: {e}")
                
        return stats
