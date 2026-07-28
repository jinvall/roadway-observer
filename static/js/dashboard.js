/* roadway-observer Dashboard — real-time stats refresh with SRP theme support */

const POLL_INTERVAL_MS = 2000;

const state = {
  status: 'offline',
  lastDetections: [],
  lastSound: [],
};

function $(id) { return document.getElementById(id); }

function formatTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString();
}

function formatUptime(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function updateStatus(status) {
  const indicator = $('status-indicator');
  const text = $('status-text');
  state.status = status;
  indicator.className = 'status ' + status;
  switch (status) {
    case 'online':
      text.textContent = 'Online';
      break;
    case 'degraded':
      text.textContent = 'Degraded';
      break;
    default:
      text.textContent = 'Offline';
  }
}

function updateStats(data) {
  $('stat-vehicles').textContent = data.vehicles_today || 0;
  $('stat-pedestrians').textContent = data.pedestrians_today || 0;
  $('stat-animals').textContent = data.animals_today || 0;
  $('stat-cyclists').textContent = data.cyclists_today || 0;
  $('stat-total').textContent = data.total_detections || 0;
  $('stat-sound').textContent = data.sound_events_today || 0;
  $('fps-display').textContent = (data.fps || 0).toFixed(1) + ' FPS';
  $('sys-inference').textContent = (data.inference_ms || 0).toFixed(1) + 'ms';
  $('sys-tracks').textContent = data.active_tracks || 0;
  $('sys-model').textContent = data.model_name || '-';
  $('sys-resolution').textContent = data.frame_width + 'x' + data.frame_height || '-';
  $('uptime').textContent = formatUptime(data.uptime_seconds || 0);

  if (data.status === 'ok') {
    updateStatus('online');
  } else if (data.stream_alive) {
    updateStatus('online');
  } else {
    updateStatus('degraded');
  }
}

function updateDetections(detections) {
  const list = $('detections-list');
  if (!detections || detections.length === 0) {
    if (state.lastDetections.length === 0) {
      list.innerHTML = '<div class="detection-empty">Waiting for detections...</div>';
    }
    return;
  }
  state.lastDetections = detections;

  list.innerHTML = detections.slice(-50).reverse().map(d => {
    const cat = d.category || 'other';
    const time = formatTime(d.timestamp);
    const label = d.class_name || 'unknown';
    const trackId = d.track_id !== undefined ? '#' + d.track_id : '';
    return `<div class="detection-item ${cat}">
      <span class="det-class">${label} <span class="det-id">${trackId}</span></span>
      <span class="det-conf">${(d.confidence * 100).toFixed(0)}%</span>
      <span class="det-time">${time}</span>
    </div>`;
  }).join('');
}

function updateSoundEvents(events) {
  const list = $('sound-list');
  if (!events || events.length === 0) {
    if (state.lastSound.length === 0) {
      list.innerHTML = '<div class="detection-empty">No sound events detected</div>';
    }
    return;
  }
  state.lastSound = events;

  list.innerHTML = events.slice(-20).reverse().map(e => {
    const type = e.event_type || 'unknown';
    const time = formatTime(e.timestamp);
    const conf = (e.confidence * 100).toFixed(0);
    return `<div class="sound-item ${type}">
      <span class="snd-type">${type}</span>
      <span>${conf}%</span>
      <span class="det-time">${time}</span>
    </div>`;
  }).join('');
}

async function fetchStats() {
  try {
    const resp = await fetch('/api/health');
    if (!resp.ok) throw new Error('HTTP ' + resp.status);
    const data = await resp.json();
    updateStats(data);
  } catch (e) {
    console.error('Stats fetch failed:', e);
    updateStatus('offline');
  }
}

async function fetchDetections() {
  try {
    const resp = await fetch('/api/detections?limit=50');
    if (!resp.ok) return;
    const data = await resp.json();
    updateDetections(data);
  } catch (e) {
  }
}

async function fetchSoundEvents() {
  try {
    const resp = await fetch('/api/sound_events?limit=20');
    if (!resp.ok) return;
    const data = await resp.json();
    updateSoundEvents(data);
  } catch (e) {
  }
}

function poll() {
  fetchStats();
  fetchDetections();
  fetchSoundEvents();
}

/* SRP Theme Integration */
const STORAGE_KEY = "srp-theme-mode";

function applyTheme(mode) {
  const root = document.documentElement;
  const safeMode = mode === "srp-light" ? "srp-light" : "srp-dark";
  root.setAttribute("data-theme", safeMode);
  try {
    localStorage.setItem(STORAGE_KEY, safeMode);
    console.log("[SRP Theme] Applied:", safeMode);
  } catch (err) {
    console.warn("[SRP Theme] Failed to persist theme mode", err);
  }
  return safeMode;
}

function getSavedTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch (err) {
    console.warn("[SRP Theme] Failed to read saved theme", err);
    return null;
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "srp-dark";
  const next = current === "srp-dark" ? "srp-light" : "srp-dark";
  return applyTheme(next);
}

function initTheme(defaultMode) {
  const saved = getSavedTheme();
  const initial = saved || defaultMode || "srp-dark";
  applyTheme(initial);
  console.log("[SRP Theme] Initialized:", initial);
}

/* Theme toggle button handler */
function setupThemeToggle() {
  const toggleBtn = $('theme-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', function() {
      const newTheme = toggleTheme();
      this.textContent = newTheme === 'srp-dark' ? 'Dark' : 'Light';
    });
  }
}

/* SRP Theme global */
window.SRPTheme = {
  initTheme,
  applyTheme,
  toggleTheme,
};

/* Start polling */
setInterval(poll, POLL_INTERVAL_MS);
poll();

/* Initialize theme on DOM ready */
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    setupThemeToggle();
    console.log('[dashboard.js] Real-time monitoring started');
  });
} else {
  initTheme();
  setupThemeToggle();
  console.log('[dashboard.js] Real-time monitoring started');
}