# 🤖 Agente IA Inteligente — Monitor de Sistemas

```
Jesús Antonio Flores González
```

[![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-3.0-black?logo=flask)](https://flask.palletsprojects.com)
[![Gemini](https://img.shields.io/badge/Google-Gemini_Pro-orange?logo=google)](https://ai.google.dev)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

Agente de inteligencia artificial que monitorea servidores Nginx y MariaDB de forma autónoma. Detecta anomalías, decide acciones correctivas y responde preguntas en lenguaje natural usando **Google Gemini Pro**.

---

## ✨ Características

| Característica | Descripción |
|---|---|
| 🔍 **Monitoreo en tiempo real** | Métricas de Nginx y MariaDB actualizadas cada 30s |
| 🤖 **IA con Gemini Pro** | Análisis de anomalías y toma de decisiones inteligente |
| 💬 **Chat natural** | Consulta al agente en español sobre el estado del sistema |
| 🗄️ **Persistencia PostgreSQL** | Historial de eventos, acciones y métricas |
| 🔐 **SSH seguro** | Conexión a VPS con clave privada via Paramiko |
| ⚡ **Acciones automáticas** | Reiniciar Nginx, matar queries, optimizar tablas |
| 📊 **Dashboard web** | Interfaz oscura moderna con auto-refresh |
| 🧠 **Aprendizaje de patrones** | El agente aprende del comportamiento histórico |

---

## 📋 Requisitos previos

- **Python** 3.9 o superior
- **PostgreSQL** 14+ (base de datos del agente)
- **Acceso SSH** al servidor con Nginx y MariaDB
- **Google Gemini API Key** → [Obtener aquí](https://ai.google.dev/)
- **pip** actualizado

---

## 🚀 Instalación

### 1. Clonar o descomprimir el proyecto

```bash
cd agente-ia-inteligente
```

### 2. Crear entorno virtual

```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
# Copiar el archivo de ejemplo
cp .env.example .env

# Editar con tus valores reales
nano .env   # o usa tu editor favorito
```

### 5. Configurar clave SSH

```bash
# Copiar tu clave privada a la carpeta keys/
cp ~/.ssh/id_rsa keys/id_rsa
chmod 600 keys/id_rsa   # Solo en Linux/macOS
```

### 6. Crear la base de datos PostgreSQL

```bash
# Conectar como superusuario
psql -U postgres

# Crear la base de datos
CREATE DATABASE agente_ia;
CREATE USER agente_user WITH PASSWORD 'tu_password';
GRANT ALL PRIVILEGES ON DATABASE agente_ia TO agente_user;
\q
```

Las tablas se crean automáticamente al iniciar el agente.

### 7. Iniciar el servidor

```bash
python app.py
```

Abre tu navegador en: **http://localhost:5000**

---

## ⚙️ Configuración

### Variables de entorno (`.env`)

```env
# ── Google Gemini ──────────────────────────────────────
GEMINI_API_KEY=AIza...          # Tu API Key de Google AI Studio
GEMINI_MODEL=gemini-pro         # Modelo a usar (gemini-pro recomendado)

# ── VPS / SSH ──────────────────────────────────────────
VPS_HOST=192.168.1.100          # IP o dominio del servidor
VPS_USER=ubuntu                 # Usuario SSH
VPS_KEY_PATH=keys/id_rsa        # Ruta relativa a la clave privada
VPS_PORT=22                     # Puerto SSH (default: 22)

# ── PostgreSQL (BD del agente) ─────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=agente_ia
DB_USER=postgres
DB_PASSWORD=tu_password

# ── MariaDB (sistema a monitorear) ────────────────────
MARIADB_HOST=192.168.1.100
MARIADB_PORT=3306
MARIADB_USER=monitor_user
MARIADB_PASSWORD=password_monitor

# ── Flask ─────────────────────────────────────────────
FLASK_ENV=development
FLASK_DEBUG=True
FLASK_PORT=5000
SECRET_KEY=clave-secreta-larga-y-aleatoria
```

### Usuario MariaDB de solo monitoreo (recomendado)

```sql
-- Conectado como root en MariaDB
CREATE USER 'monitor_user'@'%' IDENTIFIED BY 'password_seguro';
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'monitor_user'@'%';
GRANT SELECT ON *.* TO 'monitor_user'@'%';
FLUSH PRIVILEGES;
```

---

## 📁 Estructura del proyecto

```
agente-ia-inteligente/
├── app.py                  # API REST Flask 3.0 (punto de entrada)
├── agente.py               # Clase AgenteIA (lógica Gemini)
├── config.py               # Configuración central (carga .env)
├── requirements.txt        # Dependencias Python
├── .env.example            # Plantilla de variables de entorno
├── README.md               # Esta documentación
│
├── adaptadores/
│   ├── __init__.py         # Exporta las clases
│   ├── nginx.py            # Monitor Nginx via SSH (Paramiko)
│   ├── mariadb.py          # Monitor MariaDB (pymysql)
│   └── postgres.py         # Persistencia PostgreSQL (psycopg2)
│
├── templates/
│   └── index.html          # Dashboard web
│
├── static/
│   ├── css/style.css       # Estilos del dashboard
│   └── js/script.js        # Lógica frontend
│
└── keys/
    └── .gitkeep            # Carpeta para claves SSH (NO subir a git)
```

---

## 🌐 Endpoints de la API

### Sistema

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | Dashboard web |
| `GET` | `/api/health` | Estado del agente y componentes |

### Métricas

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/metricas/nginx` | Métricas actuales de Nginx |
| `GET` | `/api/metricas/mariadb` | Métricas actuales de MariaDB |

### Inteligencia Artificial

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| `POST` | `/api/analizar` | `{"metricas": {...}}` | IA analiza anomalías |
| `POST` | `/api/preguntas` | `{"pregunta": "..."}` | Chat con el agente |

### Historial

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/eventos?limite=50` | Eventos y anomalías recientes |
| `GET` | `/api/acciones` | Acciones automáticas tomadas |

### Control

| Método | Ruta | Body | Descripción |
|--------|------|------|-------------|
| `POST` | `/api/ejecutar-accion` | `{"accion": "reiniciar_nginx"}` | Reiniciar Nginx |
| `POST` | `/api/ejecutar-accion` | `{"accion": "optimizar_bd", "parametros": {"base_datos": "mydb"}}` | Optimizar tablas |
| `POST` | `/api/ejecutar-accion` | `{"accion": "matar_query", "parametros": {"proceso_id": 42}}` | Matar query lenta |

### Ejemplos con curl

```bash
# Health check
curl http://localhost:5000/api/health

# Obtener métricas Nginx
curl http://localhost:5000/api/metricas/nginx

# Analizar con IA (usa métricas actuales automáticamente)
curl -X POST http://localhost:5000/api/analizar \
     -H "Content-Type: application/json" \
     -d '{}'

# Chat con el agente
curl -X POST http://localhost:5000/api/preguntas \
     -H "Content-Type: application/json" \
     -d '{"pregunta": "¿Cuántas conexiones tiene Nginx ahora mismo?"}'

# Reiniciar Nginx
curl -X POST http://localhost:5000/api/ejecutar-accion \
     -H "Content-Type: application/json" \
     -d '{"accion": "reiniciar_nginx"}'
```

---

## 🛠️ Desarrollo

### Ejecutar en modo debug

```bash
FLASK_DEBUG=True python app.py
```

### Verificar configuración

```bash
python config.py
```

### Probar adaptadores individualmente

```python
# Probar conexión SSH/Nginx
from adaptadores.nginx import AdaptadorNginx
nginx = AdaptadorNginx("10.0.0.1", "ubuntu", "keys/id_rsa")
print(nginx.obtener_estado())
nginx.desconectar()

# Probar MariaDB
from adaptadores.mariadb import AdaptadorMariaDB
db = AdaptadorMariaDB("10.0.0.1", "monitor_user", "password")
print(db.obtener_metricas())
db.desconectar()
```

---

## 🐳 Docker (opcional)

```dockerfile
# Dockerfile básico
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

```bash
docker build -t agente-ia .
docker run -p 5000:5000 --env-file .env agente-ia
```

---

## 🔒 Seguridad

- **Nunca** subas el archivo `.env` ni la carpeta `keys/` a git
- Agrega a `.gitignore`:
  ```
  .env
  keys/*
  !keys/.gitkeep
  __pycache__/
  *.pyc
  venv/
  ```
- Usa un usuario MariaDB con permisos mínimos (solo lectura + PROCESS)
- En producción, desactiva `FLASK_DEBUG=False`
- Usa HTTPS con un proxy reverso (Nginx + certbot)

---

## ❗ Troubleshooting

### Error: `GEMINI_API_KEY no está configurada`
→ Verifica que el archivo `.env` existe y contiene la clave.

### Error: `SSH connection refused`
→ Verifica `VPS_HOST`, `VPS_PORT` y que el servidor SSH esté activo.
→ Comprueba que `VPS_KEY_PATH` apunte a la clave correcta.

### Error: `could not connect to server` (PostgreSQL)
→ Verifica que PostgreSQL esté corriendo: `pg_isready -h localhost`
→ Confirma `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`.

### Error: `Access denied for user` (MariaDB)
→ Verifica los permisos del usuario monitor en MariaDB.
→ Asegúrate que el host `%` o la IP del agente está permitida.

### El dashboard muestra "Desconectado"
→ Verifica que Flask esté corriendo en el puerto correcto.
→ Revisa la consola del navegador (F12) para errores JS.

---

## 🗺️ Roadmap

- [ ] Alertas por email/Slack cuando se detecten anomalías críticas
- [ ] Soporte para múltiples servidores VPS
- [ ] Métricas del sistema local (CPU, RAM, disco) via psutil
- [ ] Autenticación JWT para la API
- [ ] Exportar reportes en PDF
- [ ] Integración con Prometheus/Grafana
- [ ] Tests unitarios e integración

---

## 📄 Licencia

MIT License — libre para uso personal y comercial.

---

> **Agente IA Inteligente** — Construido con Flask 3.0, Google Gemini Pro, PostgreSQL, Paramiko y pymysql.
