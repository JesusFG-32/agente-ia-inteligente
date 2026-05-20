/**
 * script.js — Agente IA Inteligente Dashboard
 * ============================================
 * Lógica del dashboard: fetching de métricas, chat IA,
 * acciones de control y auto-refresh.
 */

'use strict';

// ─── Configuración ─────────────────────────────────────────────
const API_BASE = '';          // Mismo origen — Flask sirve el frontend
const REFRESH_INTERVAL = 30_000; // 30 segundos
const MAX_CHAT_HISTORY = 50;

// Estado global del dashboard
const estado = {
  nginx: null,
  mariadb: null,
  health: null,
  cargando: false,
  intervalId: null,
};

// ─── Utilidades DOM ─────────────────────────────────────────────

/** Obtiene elemento por ID, lanza error si no existe. */
function $(id) {
  const el = document.getElementById(id);
  if (!el) console.warn(`Elemento #${id} no encontrado`);
  return el;
}

/** Actualiza el texto interior de un elemento. */
function setText(id, texto) {
  const el = $(id);
  if (el) el.textContent = texto;
}

/** Muestra / oculta un elemento. */
function setVisible(id, visible) {
  const el = $(id);
  if (el) el.style.display = visible ? '' : 'none';
}

// ─── Toast notifications ─────────────────────────────────────────

function mostrarToast(mensaje, tipo = 'info', duracion = 4000) {
  const container = $('toast-container');
  if (!container) return;

  const iconos = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const toast = document.createElement('div');
  toast.className = `toast ${tipo}`;
  toast.innerHTML = `<span>${iconos[tipo] ?? 'ℹ️'}</span><span>${mensaje}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = '0.3s ease';
    setTimeout(() => toast.remove(), 350);
  }, duracion);
}

// ─── Fetch helper ────────────────────────────────────────────────

async function apiFetch(url, opciones = {}) {
  try {
    const res = await fetch(API_BASE + url, {
      headers: { 'Content-Type': 'application/json' },
      ...opciones,
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
    return data;
  } catch (err) {
    console.error(`API Error [${url}]:`, err.message);
    throw err;
  }
}

// ─── Formateo de datos ──────────────────────────────────────────

function formatFecha(isoString) {
  if (!isoString) return '—';
  try {
    return new Date(isoString).toLocaleString('es-MX', {
      day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });
  } catch { return isoString; }
}

function formatSeveridad(sev) {
  const mapa = {
    info:    { clase: 'blue',   label: 'INFO' },
    warning: { clase: 'yellow', label: 'WARN' },
    error:   { clase: 'red',    label: 'ERROR' },
    critico: { clase: 'red',    label: 'CRÍTICO' },
  };
  return mapa[sev] ?? { clase: 'blue', label: sev?.toUpperCase() ?? 'INFO' };
}

// ─── Health check ────────────────────────────────────────────────

async function actualizarHealth() {
  try {
    const data = await apiFetch('/api/health');
    estado.health = data.health;

    const badge = $('status-badge');
    if (badge) {
      badge.className = 'status-badge ok';
      badge.innerHTML = '<span class="status-dot"></span>Sistema Operativo';
    }

    // Indicadores de componentes
    const { componentes } = data.health;
    actualizarIndicador('ind-gemini',   componentes.gemini,      'Gemini');
    actualizarIndicador('ind-postgres', componentes.postgres,    'PostgreSQL');
    actualizarIndicador('ind-nginx',    componentes.nginx_ssh,   'Nginx SSH');
    actualizarIndicador('ind-mariadb',  componentes.mariadb,     'MariaDB');

  } catch (err) {
    const badge = $('status-badge');
    if (badge) {
      badge.className = 'status-badge error';
      badge.innerHTML = '<span class="status-dot"></span>Desconectado';
    }
  }
}

function actualizarIndicador(id, activo, nombre) {
  const el = $(id);
  if (!el) return;
  el.className = `pill ${activo ? 'green' : 'red'}`;
  el.textContent = `${activo ? '●' : '○'} ${nombre}`;
}

// ─── Métricas Nginx ──────────────────────────────────────────────

async function actualizarMetricasNginx() {
  try {
    const data = await apiFetch('/api/metricas/nginx');
    estado.nginx = data.metricas;
    const m = data.metricas;

    if (m.ok) {
      const activo = m.estado?.activo;
      setText('nginx-estado', activo ? 'Activo' : 'Inactivo');
      setText('nginx-conexiones', m.conexiones?.total ?? '—');
      setText('nginx-procesos', m.procesos?.cantidad ?? '—');

      const badge = $('nginx-badge');
      if (badge) {
        badge.className = `pill ${activo ? 'green' : 'red'}`;
        badge.textContent = activo ? 'RUNNING' : 'STOPPED';
      }

      // Errores recientes
      const errores = m.logs_error_recientes ?? [];
      const cont = $('nginx-errores');
      if (cont) {
        cont.innerHTML = errores.length
          ? errores.slice(-5).map(l =>
              `<div class="text-sm mono text-muted" style="margin-bottom:4px;word-break:break-all">${escapeHtml(l)}</div>`
            ).join('')
          : '<div class="empty-state text-sm">Sin errores recientes 🎉</div>';
      }
    } else {
      setText('nginx-estado', 'Error');
      mostrarToast(`Nginx: ${m.error}`, 'error');
    }
  } catch (err) {
    setText('nginx-estado', 'Sin conexión');
  }
}

// ─── Métricas MariaDB ────────────────────────────────────────────

async function actualizarMetricasMariaDB() {
  try {
    const data = await apiFetch('/api/metricas/mariadb');
    estado.mariadb = data.metricas;
    const m = data.metricas;

    if (m.ok) {
      const conexiones = m.conexiones?.total ?? 0;
      setText('mariadb-conexiones', conexiones);

      const estado_gral = m.estado_general ?? {};
      setText('mariadb-queries',   estado_gral.Questions ?? '—');
      setText('mariadb-lentas',    estado_gral.Slow_queries ?? '0');
      setText('mariadb-uptime',    formatUptime(estado_gral.Uptime));

      const badgeEl = $('mariadb-badge');
      if (badgeEl) {
        badgeEl.className = 'pill green';
        badgeEl.textContent = 'CONNECTED';
      }

      // Queries lentas
      const lentas = m.queries_lentas?.queries ?? [];
      const cont = $('mariadb-lentas-list');
      if (cont) {
        cont.innerHTML = lentas.length
          ? lentas.map(q =>
              `<div class="event-item">
                <span class="event-dot warning"></span>
                <div class="event-body">
                  <div class="event-desc">${escapeHtml(q.Info ?? 'Query sin info')}</div>
                  <div class="event-meta">PID: ${q.Id} · ${q.Time}s · ${q.db ?? 'N/A'}</div>
                </div>
                <button class="btn btn-danger btn-sm" onclick="matarQuery(${q.Id})">Kill</button>
              </div>`
            ).join('')
          : '<div class="empty-state text-sm">Sin queries lentas ✓</div>';
      }
    } else {
      setText('mariadb-conexiones', 'Error');
      mostrarToast(`MariaDB: ${m.error}`, 'error');
    }
  } catch (err) {
    setText('mariadb-conexiones', 'Sin conexión');
  }
}

function formatUptime(segundos) {
  if (!segundos) return '—';
  const s = parseInt(segundos);
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
}

// ─── Dashboard completo ──────────────────────────────────────────

async function actualizarDashboard() {
  if (estado.cargando) return;
  estado.cargando = true;

  setText('last-update', 'Actualizando...');

  try {
    await Promise.allSettled([
      actualizarHealth(),
      actualizarMetricasNginx(),
      actualizarMetricasMariaDB(),
      cargarEventos(),
    ]);
    setText('last-update', `Actualizado: ${new Date().toLocaleTimeString('es-MX')}`);
  } finally {
    estado.cargando = false;
  }
}

// ─── Análisis IA ─────────────────────────────────────────────────

async function analizarAnomalias() {
  const btn = $('btn-analizar');
  if (btn) {
    btn.disabled = true;
    btn.classList.add('btn-loading');
  }

  mostrarToast('Analizando métricas con IA...', 'info', 2000);
  const panel = $('analisis-panel');
  if (panel) panel.className = 'analysis-panel';

  try {
    // Construir payload con métricas actuales
    const payload = {};
    if (estado.nginx)   payload.nginx   = estado.nginx;
    if (estado.mariadb) payload.mariadb = estado.mariadb;

    const data = await apiFetch('/api/analizar', {
      method: 'POST',
      body: JSON.stringify({ metricas: payload }),
    });

    const analisis = data.analisis;
    renderizarAnalisis(analisis);
    mostrarToast(`Análisis completado: ${analisis.anomalias?.length ?? 0} anomalías detectadas`, 'success');
  } catch (err) {
    mostrarToast(`Error en análisis: ${err.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.classList.remove('btn-loading');
    }
  }
}

function renderizarAnalisis(analisis) {
  const panel = $('analisis-panel');
  if (!panel) return;

  const anomalias = analisis.anomalias ?? [];
  const recs = analisis.recomendaciones ?? [];

  panel.innerHTML = `
    <div class="panel-header" style="margin-bottom:1rem">
      <span>🤖 Análisis IA — ${new Date().toLocaleTimeString('es-MX')}</span>
      <span class="pill ${anomalias.length ? 'red' : 'green'}">${anomalias.length} anomalías</span>
    </div>
    <p class="text-sm" style="margin-bottom:1rem;color:var(--text-secondary)">${escapeHtml(analisis.resumen ?? '')}</p>
    ${anomalias.length ? `
      <div class="section-title">Anomalías detectadas</div>
      ${anomalias.map(a => `
        <div class="analysis-anomaly">
          <span class="pill ${severidadColor(a.severidad)}">${a.severidad?.toUpperCase()}</span>
          <span class="text-sm">${escapeHtml(a.descripcion)}</span>
        </div>
      `).join('')}
    ` : '<div class="empty-state">✅ Sin anomalías detectadas</div>'}
    ${recs.length ? `
      <div class="section-title" style="margin-top:1rem">Recomendaciones</div>
      <ul style="padding-left:1.2rem">
        ${recs.map(r => `<li class="text-sm" style="margin-bottom:4px;color:var(--text-secondary)">${escapeHtml(r)}</li>`).join('')}
      </ul>
    ` : ''}
  `;
  panel.className = 'analysis-panel visible';
}

function severidadColor(sev) {
  return { info: 'blue', warning: 'yellow', error: 'red', critico: 'red' }[sev] ?? 'blue';
}

// ─── Chat IA ──────────────────────────────────────────────────────

async function enviarPregunta() {
  const input = $('chat-input');
  if (!input) return;
  const texto = input.value.trim();
  if (!texto) return;

  agregarMensajeChat('user', texto);
  input.value = '';

  const btn = $('btn-enviar');
  if (btn) { btn.disabled = true; btn.classList.add('btn-loading'); }

  try {
    const data = await apiFetch('/api/preguntas', {
      method: 'POST',
      body: JSON.stringify({ pregunta: texto }),
    });
    agregarMensajeChat('agent', data.respuesta);
  } catch (err) {
    agregarMensajeChat('agent', `❌ Error: ${err.message}`);
  } finally {
    if (btn) { btn.disabled = false; btn.classList.remove('btn-loading'); }
    input.focus();
  }
}

function agregarMensajeChat(rol, texto) {
  const container = $('chat-messages');
  if (!container) return;

  const div = document.createElement('div');
  div.className = `chat-msg ${rol}`;

  // Convertir saltos de línea en <br> para el agente
  if (rol === 'agent') {
    div.innerHTML = `<pre>${escapeHtml(texto)}</pre>`;
  } else {
    div.textContent = texto;
  }

  container.appendChild(div);

  // Limitar mensajes visibles
  const mensajes = container.querySelectorAll('.chat-msg');
  if (mensajes.length > MAX_CHAT_HISTORY) {
    mensajes[0].remove();
  }

  container.scrollTop = container.scrollHeight;
}

// ─── Eventos ──────────────────────────────────────────────────────

async function cargarEventos() {
  try {
    const data = await apiFetch('/api/eventos?limite=30');
    renderizarEventos(data.eventos ?? []);
  } catch (err) {
    console.warn('Error cargando eventos:', err.message);
  }
}

function renderizarEventos(eventos) {
  const lista = $('eventos-lista');
  if (!lista) return;

  if (!eventos.length) {
    lista.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">📋</div>
        Sin eventos registrados aún
      </div>`;
    return;
  }

  lista.innerHTML = eventos.map(ev => {
    const sev = formatSeveridad(ev.severidad);
    return `
      <div class="event-item">
        <div class="event-dot ${ev.severidad ?? 'info'}"></div>
        <div class="event-body">
          <div class="event-desc">${escapeHtml(ev.descripcion ?? ev.tipo)}</div>
          <div class="event-meta">
            <span class="pill ${sev.clase}">${sev.label}</span>
            ${formatFecha(ev.creado_en)}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// ─── Acciones de control ─────────────────────────────────────────

async function reiniciarNginx() {
  if (!confirm('¿Reiniciar Nginx? El servicio estará brevemente inaccesible.')) return;
  await ejecutarAccion('reiniciar_nginx', {}, $('btn-reiniciar-nginx'));
}

async function optimizarBD() {
  const bd = prompt('Nombre de la base de datos a optimizar:', 'mi_base_de_datos');
  if (!bd) return;
  await ejecutarAccion('optimizar_bd', { base_datos: bd }, $('btn-optimizar-bd'));
}

async function matarQuery(procesoId) {
  if (!confirm(`¿Terminar query con PID ${procesoId}?`)) return;
  await ejecutarAccion('matar_query', { proceso_id: procesoId }, null);
}

async function ejecutarAccion(accion, parametros, btnEl) {
  if (btnEl) { btnEl.disabled = true; btnEl.classList.add('btn-loading'); }
  mostrarToast(`Ejecutando: ${accion}...`, 'info', 2000);

  try {
    const data = await apiFetch('/api/ejecutar-accion', {
      method: 'POST',
      body: JSON.stringify({ accion, parametros }),
    });
    const res = data.resultado;
    if (res?.exito !== false) {
      mostrarToast(res?.mensaje ?? `${accion} completado`, 'success');
      setTimeout(actualizarDashboard, 2000);
    } else {
      mostrarToast(`Error: ${res?.mensaje}`, 'error');
    }
  } catch (err) {
    mostrarToast(`Error ejecutando ${accion}: ${err.message}`, 'error');
  } finally {
    if (btnEl) { btnEl.disabled = false; btnEl.classList.remove('btn-loading'); }
  }
}

// ─── Auto-refresh ─────────────────────────────────────────────────

function iniciarAutoRefresh() {
  if (estado.intervalId) clearInterval(estado.intervalId);
  estado.intervalId = setInterval(actualizarDashboard, REFRESH_INTERVAL);
  console.log(`🔄 Auto-refresh cada ${REFRESH_INTERVAL / 1000}s activado`);
}

function detenerAutoRefresh() {
  if (estado.intervalId) {
    clearInterval(estado.intervalId);
    estado.intervalId = null;
  }
}

// ─── Seguridad ────────────────────────────────────────────────────

function escapeHtml(str) {
  if (typeof str !== 'string') return String(str ?? '');
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ─── Event listeners ──────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Botones de header/acciones
  const btnAnalizar = $('btn-analizar');
  if (btnAnalizar) btnAnalizar.addEventListener('click', analizarAnomalias);

  const btnReiniciar = $('btn-reiniciar-nginx');
  if (btnReiniciar) btnReiniciar.addEventListener('click', reiniciarNginx);

  const btnOptimizar = $('btn-optimizar-bd');
  if (btnOptimizar) btnOptimizar.addEventListener('click', optimizarBD);

  const btnRefresh = $('btn-refresh');
  if (btnRefresh) btnRefresh.addEventListener('click', () => {
    actualizarDashboard();
    mostrarToast('Actualizando datos...', 'info', 1500);
  });

  // Chat — botón enviar
  const btnEnviar = $('btn-enviar');
  if (btnEnviar) btnEnviar.addEventListener('click', enviarPregunta);

  // Chat — tecla Enter
  const chatInput = $('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        enviarPregunta();
      }
    });
  }

  // Iniciar dashboard
  actualizarDashboard();
  iniciarAutoRefresh();

  // Mensaje de bienvenida en el chat
  agregarMensajeChat('agent',
    '¡Hola! Soy tu Agente IA de monitoreo 🤖\n\n' +
    'Puedo ayudarte con:\n' +
    '• Estado de Nginx y MariaDB\n' +
    '• Análisis de anomalías\n' +
    '• Optimización de bases de datos\n\n' +
    '¿En qué puedo ayudarte?'
  );
});
