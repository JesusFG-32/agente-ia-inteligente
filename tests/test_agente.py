import unittest
from unittest.mock import patch, MagicMock
import json

from agente import AgenteIA, PROMPT_ANALISIS, PROMPT_RESPUESTA, PROMPT_DECISION

class TestAgenteIA(unittest.TestCase):
    
    def setUp(self):
        # Configuración básica para los tests (sin conexiones reales)
        self.gemini_key = "test_key"
        self.mongo_uri = "mongodb://test_uri"
        self.pg_config = {"host": "localhost", "dbname": "test_db", "user": "test_user"}
        
        # Parchear las conexiones en __init__ para evitar conectar a servicios reales
        patcher_gemini = patch('agente.genai.configure')
        patcher_mongo = patch('agente.MongoClient')
        patcher_pg = patch('agente.psycopg2.connect')
        
        self.mock_gemini_config = patcher_gemini.start()
        self.mock_mongo = patcher_mongo.start()
        self.mock_pg = patcher_pg.start()
        
        # Asegurar que los mocks se detengan después del test
        self.addCleanup(patcher_gemini.stop)
        self.addCleanup(patcher_mongo.stop)
        self.addCleanup(patcher_pg.stop)

        # Crear instancia de AgenteIA
        self.agente = AgenteIA(self.gemini_key, self.mongo_uri, self.pg_config)
        
        # Mock del modelo de Gemini
        self.agente.modelo = MagicMock()
        
        # Mock de DBs
        self.agente.db_mongo = MagicMock()
        self.agente.pg_conn = MagicMock()

    def test_conexiones_mongodb_postgresql(self):
        """Verifica que __init__ llama a las funciones de conexión correctamente."""
        self.mock_gemini_config.assert_called_once_with(api_key=self.gemini_key)
        self.mock_mongo.assert_called_once_with(self.mongo_uri, serverSelectionTimeoutMS=5000)
        self.mock_pg.assert_called_once_with(**self.pg_config)

    def test_analizar_metricas_detecta_anomalias(self):
        """Verifica el flujo de analizar_metricas con Gemini y detección local."""
        metricas = {"nginx": {"active_connections": 200}}
        
        # Configurar la respuesta simulada de Gemini
        respuesta_mock = MagicMock()
        respuesta_json = {
            "anomalias": [
                {"tipo": "conexiones_altas", "severidad": "ALTA", "descripcion": "Exceso"}
            ],
            "estado_general": "ALERTA",
            "resumen": "Resumen de prueba"
        }
        respuesta_mock.text = json.dumps(respuesta_json)
        self.agente.modelo.generate_content.return_value = respuesta_mock
        
        # Mock para guardar_evento de postgres
        self.agente.guardar_evento = MagicMock(return_value=1)
        
        resultado = self.agente.analizar_metricas(metricas)
        
        # Verificaciones
        self.agente.modelo.generate_content.assert_called_once()
        self.assertEqual(resultado["estado_general"], "ALERTA")
        self.assertTrue(len(resultado["anomalias"]) > 0)
        # Verifica que se intentó guardar el evento en Postgres
        self.agente.guardar_evento.assert_called_once()

    def test_generar_respuesta_usa_contexto(self):
        """Verifica la generación de respuesta usando contexto histórico."""
        pregunta = "¿Qué pasó ayer?"
        contexto = [{"usuario_pregunta": "Hola", "respuesta_agente": "Hola, ¿en qué te ayudo?"}]
        
        respuesta_mock = MagicMock()
        respuesta_mock.text = "Ayer hubo un pico de CPU."
        self.agente.modelo.generate_content.return_value = respuesta_mock
        
        respuesta = self.agente.generar_respuesta(pregunta, contexto_historico=contexto)
        
        self.assertEqual(respuesta, "Ayer hubo un pico de CPU.")
        self.agente.modelo.generate_content.assert_called_once()
        
        # Verificar que el prompt contiene el contexto y la pregunta
        call_args = self.agente.modelo.generate_content.call_args[0][0]
        self.assertIn("Hola, ¿en qué te ayudo?", call_args)
        self.assertIn("¿Qué pasó ayer?", call_args)

    def test_guardar_contexto_chat(self):
        """Verifica que guardar_contexto_chat llama a MongoDB."""
        self.agente._guardar_en_mongodb = MagicMock(return_value=True)
        resultado = self.agente.guardar_contexto_chat("pregunta", "respuesta", {"usuario_id": "123"})
        
        self.assertTrue(resultado)
        self.agente._guardar_en_mongodb.assert_called_once()
        args = self.agente._guardar_en_mongodb.call_args[0]
        self.assertEqual(args[0], "chat_history")
        self.assertIn("usuario_pregunta", args[1])

    def test_aprender_patron(self):
        """Verifica el método aprender_patron."""
        self.agente._guardar_en_mongodb = MagicMock(return_value=True)
        resultado = self.agente.aprender_patron("cpu_alta", {"hora": "10:00"})
        
        self.assertTrue(resultado)
        self.agente._guardar_en_mongodb.assert_called_once()
        args = self.agente._guardar_en_mongodb.call_args[0]
        self.assertEqual(args[0], "patrones")
        self.assertEqual(args[1]["tipo_patron"], "cpu_alta")

    def test_decidir_accion(self):
        """Verifica la decisión de acción autónoma mediante Gemini."""
        anomalia = {"tipo": "query_lenta"}
        
        respuesta_mock = MagicMock()
        decision_json = {
            "accion": "matar_query",
            "parametros": {"pid": 123},
            "ejecutar_automaticamente": True,
            "razon": "Consumo excesivo",
            "rollback_plan": "N/A"
        }
        respuesta_mock.text = json.dumps(decision_json)
        self.agente.modelo.generate_content.return_value = respuesta_mock
        
        self.agente.guardar_evento = MagicMock()
        
        resultado = self.agente.decidir_accion(anomalia)
        
        self.assertEqual(resultado["accion"], "matar_query")
        self.assertTrue(resultado["ejecutar_automaticamente"])
        self.agente.guardar_evento.assert_called_once()

    def test_limpiar_respuesta_json(self):
        """Verifica el helper de limpieza de JSON (eliminar markdown)."""
        texto_con_markdown = "```json\n{\n  \"anomalias\": []\n}\n```"
        resultado = self.agente._limpiar_respuesta_json(texto_con_markdown)
        self.assertEqual(resultado, {"anomalias": []})
        
        texto_sin_markdown = '{"clave": "valor"}'
        resultado2 = self.agente._limpiar_respuesta_json(texto_sin_markdown)
        self.assertEqual(resultado2, {"clave": "valor"})
        
        texto_invalido = "esto no es json"
        resultado3 = self.agente._limpiar_respuesta_json(texto_invalido)
        self.assertEqual(resultado3, {})

    def test_prompts_generados_correctamente(self):
        """Verifica que los métodos de generación de prompts funcionen."""
        metricas = {"cpu": 90}
        prompt_analisis = self.agente.generar_prompt_analisis(metricas)
        self.assertIn("90", prompt_analisis)
        self.assertIn("Métricas:", prompt_analisis)
        
        prompt_respuesta = self.agente.generar_prompt_respuesta("Hola", [])
        self.assertIn("No hay contexto previo.", prompt_respuesta)
        self.assertIn("Hola", prompt_respuesta)

if __name__ == '__main__':
    unittest.main()
