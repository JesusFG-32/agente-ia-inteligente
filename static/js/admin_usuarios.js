/**
 * admin_usuarios.js — Panel de administración de usuarios
 * ========================================================
 * CRUD de usuarios + visualización de la matriz de permisos por rol.
 * Requiere rol 'admin' (verificado por el backend).
 */

'use strict';

const TOKEN_KEY = 'agente_ia_token';
const USER_KEY  = 'agente_ia_user';

// ─── Helpers ────────────────────────────────────────────────

function getToken() { return localStorage.getItem(TOKEN_KEY); }

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  window.location.href = '/login';
}

function escapeHtml(str) {
  if (typeof str !== 'string') return String(str ?? '');
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function formatFecha(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('es-MX', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
}

function toast(mensaje, tipo = 'info', duracion = 3500) {
  const c = document.getElementById('toast-container');
  if (!c) return;
  const iconos = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const el = document.createElement('div');
  el.className = `toast ${tipo}`;
  el.innerHTML = `<span>${iconos[tipo] ?? 'ℹ️'}</span><span>${escapeHtml(mensaje)}</span>`;
  c.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = '0.3s ease';
    setTimeout(() => el.remove(), 350);
  }, duracion);
}

async function api(url, opciones = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(opciones.headers ?? {}),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(url, { ...opciones, headers });
  if (res.status === 401) {
    toast('Sesión expirada', 'warning');
    setTimeout(logout, 800);
    throw new Error('No autenticado');
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error ?? `HTTP ${res.status}`);
  return data;
}

// ─── Estado ─────────────────────────────────────────────────

const estado = {
  usuarioActual: null,
  usuarios: [],
  roles: {},
  permisos: {},
};

// ─── Bootstrap ──────────────────────────────────────────────

async function bootstrap() {
  if (!getToken()) { window.location.href = '/login'; return; }

  try {
    const me = await api('/api/auth/me');
    estado.usuarioActual = me.usuario;
    if (estado.usuarioActual.rol !== 'admin') {
      toast('Acceso restringido a administradores', 'error');
      setTimeout(() => { window.location.href = '/'; }, 1500);
      return;
    }
  } catch {
    return;
  }

  // Pintar usuario actual en header
  const ui = document.getElementById('user-info');
  if (ui) {
    ui.className = 'pill red';
    ui.textContent = `👤 ${estado.usuarioActual.username} · ADMIN`;
  }

  // Cargar todo en paralelo
  await Promise.all([cargarRoles(), cargarUsuarios()]);
}

// ─── Roles y permisos ───────────────────────────────────────

async function cargarRoles() {
  try {
    const data = await api('/api/auth/roles');
    estado.roles = data.roles;
    estado.permisos = data.permisos;
    renderMatrizPermisos();
  } catch (err) {
    toast(`Error cargando roles: ${err.message}`, 'error');
  }
}

function renderMatrizPermisos() {
  const cont = document.getElementById('permisos-matrix');
  if (!cont) return;

  const roles = Object.keys(estado.roles);
  const permisos = Object.keys(estado.permisos);

  cont.innerHTML = `
    <div class="table-wrap">
      <table class="permisos-table">
        <thead>
          <tr>
            <th style="text-align:left">Permiso</th>
            ${roles.map(r => `<th>${r.toUpperCase()}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${permisos.map(p => `
            <tr>
              <td style="text-align:left">
                <strong class="mono">${escapeHtml(p)}</strong>
                <div class="text-sm text-muted">${escapeHtml(estado.permisos[p])}</div>
              </td>
              ${roles.map(r => `
                <td>${estado.roles[r].includes(p)
                  ? '<span class="pill green">✓</span>'
                  : '<span class="pill" style="background:rgba(255,255,255,0.05);color:var(--text-muted)">—</span>'}
                </td>
              `).join('')}
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

// ─── Usuarios ───────────────────────────────────────────────

async function cargarUsuarios() {
  try {
    const data = await api('/api/usuarios');
    estado.usuarios = data.usuarios;
    renderUsuarios();
  } catch (err) {
    toast(`Error cargando usuarios: ${err.message}`, 'error');
  }
}

function renderUsuarios() {
  const tbody = document.getElementById('users-tbody');
  if (!tbody) return;

  if (!estado.usuarios.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-state">Sin usuarios</td></tr>';
    return;
  }

  const yo = estado.usuarioActual.id;
  tbody.innerHTML = estado.usuarios.map(u => {
    const esYo = u.id === yo;
    const rolClass = u.rol === 'admin' ? 'red' : u.rol === 'operator' ? 'yellow' : 'green';
    return `
      <tr data-id="${escapeHtml(u.id)}">
        <td class="mono text-sm" title="${escapeHtml(u.id)}">${escapeHtml(u.id.slice(0, 8))}…</td>
        <td>${escapeHtml(u.email)}${esYo ? ' <span class="pill blue" style="font-size:0.65rem">TÚ</span>' : ''}</td>
        <td>${escapeHtml(u.username)}</td>
        <td>
          <select class="select-rol auth-input" ${esYo ? 'disabled' : ''}>
            <option value="viewer"   ${u.rol === 'viewer'   ? 'selected' : ''}>viewer</option>
            <option value="operator" ${u.rol === 'operator' ? 'selected' : ''}>operator</option>
            <option value="admin"    ${u.rol === 'admin'    ? 'selected' : ''}>admin</option>
          </select>
        </td>
        <td>
          <label class="toggle-activo">
            <input type="checkbox" class="check-activo" ${u.activo ? 'checked' : ''} ${esYo ? 'disabled' : ''} />
            <span class="pill ${u.activo ? 'green' : 'red'}">${u.activo ? 'ACTIVO' : 'INACTIVO'}</span>
          </label>
        </td>
        <td class="text-sm text-muted">${formatFecha(u.ultimo_login)}</td>
        <td class="actions-cell">
          <button class="btn btn-primary btn-sm btn-guardar">💾</button>
          <button class="btn btn-danger btn-sm btn-eliminar" ${esYo ? 'disabled title="No puedes eliminarte"' : ''}>🗑️</button>
        </td>
      </tr>
    `;
  }).join('');

  // Wire up botones de cada fila
  tbody.querySelectorAll('tr').forEach(tr => {
    const id = tr.dataset.id;
    tr.querySelector('.btn-guardar')?.addEventListener('click', () => guardarUsuario(id, tr));
    tr.querySelector('.btn-eliminar')?.addEventListener('click', () => eliminarUsuario(id));
  });
}

async function guardarUsuario(id, tr) {
  const rol = tr.querySelector('.select-rol').value;
  const activo = tr.querySelector('.check-activo').checked;

  try {
    await api(`/api/usuarios/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ rol, activo }),
    });
    toast('Usuario actualizado', 'success');
    cargarUsuarios();
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  }
}

async function eliminarUsuario(id) {
  const usuario = estado.usuarios.find(u => u.id === id);
  if (!usuario) return;
  if (!confirm(`¿Eliminar permanentemente al usuario "${usuario.email}"?`)) return;

  try {
    await api(`/api/usuarios/${id}`, { method: 'DELETE' });
    toast('Usuario eliminado', 'success');
    cargarUsuarios();
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  }
}

async function crearUsuario(ev) {
  ev.preventDefault();
  const email    = document.getElementById('nu-email').value.trim().toLowerCase();
  const username = document.getElementById('nu-username').value.trim();
  const password = document.getElementById('nu-password').value;
  const rol      = document.getElementById('nu-rol').value;

  if (!email || !username || password.length < 6) {
    toast('Datos incompletos o password < 6 caracteres', 'warning');
    return;
  }

  const btn = ev.target.querySelector('button[type="submit"]');
  btn.disabled = true;
  btn.classList.add('btn-loading');

  try {
    await api('/api/usuarios', {
      method: 'POST',
      body: JSON.stringify({ email, username, password, rol }),
    });
    toast(`Usuario ${email} creado`, 'success');
    ev.target.reset();
    cargarUsuarios();
  } catch (err) {
    toast(`Error: ${err.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.classList.remove('btn-loading');
  }
}

// ─── Wire-up ────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-logout')?.addEventListener('click', () => {
    if (confirm('¿Cerrar sesión?')) logout();
  });
  document.getElementById('form-crear-usuario')?.addEventListener('submit', crearUsuario);
  bootstrap();
});
