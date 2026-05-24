/**
 * login.js — Página de login del Agente IA
 * ==========================================
 * Envía email/password al backend, guarda el JWT y redirige al dashboard.
 */

'use strict';

const TOKEN_KEY = 'agente_ia_token';
const USER_KEY  = 'agente_ia_user';

// Si ya hay un token válido, redirigir al dashboard
(async function comprobarSesion() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return;
  try {
    const res = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      window.location.href = '/';
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
    }
  } catch { /* sin red, dejar al usuario en login */ }
})();

// Toast helper (versión simplificada — duplica el del dashboard a propósito
// para que login funcione standalone)
function mostrarToast(mensaje, tipo = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const iconos = { success: '✅', error: '❌', info: 'ℹ️', warning: '⚠️' };
  const toast = document.createElement('div');
  toast.className = `toast ${tipo}`;
  toast.innerHTML = `<span>${iconos[tipo] ?? 'ℹ️'}</span><span>${mensaje}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = '0.3s ease';
    setTimeout(() => toast.remove(), 350);
  }, 3500);
}

function mostrarError(mensaje) {
  const box = document.getElementById('login-error');
  if (!box) return;
  box.textContent = mensaje;
  box.classList.add('visible');
  setTimeout(() => box.classList.remove('visible'), 6000);
}

// ─── Submit del formulario ─────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('login-form');
  const btn  = document.getElementById('btn-login');

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const email    = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    if (!email || !password) {
      mostrarError('Email y contraseña son requeridos');
      return;
    }

    btn.disabled = true;
    btn.classList.add('btn-loading');

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();

      if (!res.ok || !data.ok) {
        mostrarError(data.error ?? 'No se pudo iniciar sesión');
        mostrarToast(data.error ?? 'Login fallido', 'error');
        return;
      }

      // Persistir token y usuario
      localStorage.setItem(TOKEN_KEY, data.token);
      localStorage.setItem(USER_KEY, JSON.stringify(data.usuario));
      mostrarToast(`¡Bienvenido, ${data.usuario.username}!`, 'success');

      // Pequeña pausa visual antes de redirigir
      setTimeout(() => { window.location.href = '/'; }, 400);
    } catch (err) {
      mostrarError(`Error de red: ${err.message}`);
      mostrarToast('No se pudo contactar al servidor', 'error');
    } finally {
      btn.disabled = false;
      btn.classList.remove('btn-loading');
    }
  });
});
