/**
 * pipeline.js — client-side logic for darkhorse_neuralynx Django app
 *
 * Exports (called from inline script blocks in templates):
 *   startDashboardPolling(activePk)
 *   initSessionDetail(pk, statusUrl, startUrl, stopUrl, csrf, initialStatus)
 */

// ── Utilities ────────────────────────────────────────────────────────────────

async function apiPost(url, csrf) {
  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'X-CSRFToken': csrf,
      'Content-Type': 'application/json',
    },
  });
  return resp.json();
}

async function apiGet(url) {
  const resp = await fetch(url);
  return resp.json();
}

// ── Dashboard polling ─────────────────────────────────────────────────────────
/**
 * When a session is active, poll its status endpoint every 3 s and update
 * the banner's status label and packet counter.
 */
function startDashboardPolling(activePk) {
  if (!activePk) return;

  const statusEl  = document.getElementById('banner-status');
  const packetsEl = document.getElementById('banner-packets');
  if (!statusEl) return;

  const statusUrl = `/sessions/${activePk}/status/`;

  async function poll() {
    try {
      const data = await apiGet(statusUrl);
      if (statusEl)  statusEl.textContent  = data.status_label || '';
      if (packetsEl) packetsEl.textContent = (data.packets_sent || 0).toLocaleString();

      // Stop polling once session is no longer active
      if (!data.is_active) {
        // Reload page to update table rows / action buttons
        setTimeout(() => location.reload(), 800);
        return;
      }
    } catch { /* ignore transient errors */ }
    setTimeout(poll, 3000);
  }

  setTimeout(poll, 1500);
}


// ── Session detail ─────────────────────────────────────────────────────────────
/**
 * Called from session_detail.html.
 * - Polls status endpoint every 2 s while session is active
 * - Updates status badge, log terminal, packet counter, duration
 * - Wires up Start / Stop buttons
 */
function initSessionDetail(pk, statusUrl, startUrl, stopUrl, csrf, initialStatus) {
  let autoScroll  = true;
  let polling     = false;
  let pollTimeout = null;

  const logContent = document.getElementById('log-content');
  const logContainer = document.getElementById('log-container');
  const statusBadge  = document.getElementById('status-badge');
  const packetsEl    = document.getElementById('packets-display');
  const durationEl   = document.getElementById('duration-display');
  const btnStart     = document.getElementById('btn-start');
  const btnStop      = document.getElementById('btn-stop');

  // ── Auto-scroll toggle ──────────────────────────────────────────────────
  const scrollToggle = document.getElementById('btn-scroll-toggle');
  scrollToggle?.addEventListener('click', () => {
    autoScroll = !autoScroll;
    scrollToggle.classList.toggle('btn-outline-secondary', !autoScroll);
    scrollToggle.innerHTML = autoScroll
      ? '<i class="bi bi-arrow-down-circle"></i> Auto-scroll'
      : '<i class="bi bi-pause-circle"></i> Paused';
  });

  // ── Copy log ────────────────────────────────────────────────────────────
  document.getElementById('btn-copy-log')?.addEventListener('click', () => {
    const text = logContent?.textContent || '';
    navigator.clipboard.writeText(text).then(() => {
      const btn = document.getElementById('btn-copy-log');
      btn.innerHTML = '<i class="bi bi-check"></i>';
      setTimeout(() => { btn.innerHTML = '<i class="bi bi-clipboard"></i>'; }, 1500);
    });
  });

  // ── RC file preview ─────────────────────────────────────────────────────
  document.getElementById('btn-load-rc')?.addEventListener('click', async () => {
    const url = document.getElementById('btn-load-rc').dataset.url;
    try {
      const data = await apiGet(url);
      if (data.content) {
        document.getElementById('rc-content').textContent = data.content;
        document.getElementById('rc-preview').style.display = '';
        document.getElementById('rc-placeholder').style.display = 'none';
      } else {
        document.getElementById('rc-placeholder').textContent =
          `Error: ${data.error || 'Unknown error'}`;
      }
    } catch (e) {
      document.getElementById('rc-placeholder').textContent = `Error: ${e.message}`;
    }
  });

  // ── Start button ────────────────────────────────────────────────────────
  btnStart?.addEventListener('click', async () => {
    btnStart.disabled = true;
    btnStart.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Starting…';
    try {
      const data = await apiPost(startUrl, csrf);
      if (data.error) {
        alert(`Could not start session: ${data.error}`);
        btnStart.disabled = false;
        btnStart.innerHTML = '<i class="bi bi-play-fill me-1"></i>Start';
      } else {
        startPolling();
        btnStart.style.display = 'none';
        if (btnStop) btnStop.style.display = '';
      }
    } catch (e) {
      alert(`Request failed: ${e.message}`);
      btnStart.disabled = false;
    }
  });

  // ── Stop button ─────────────────────────────────────────────────────────
  btnStop?.addEventListener('click', async () => {
    if (!confirm('Stop this session? DHN-AQ will be terminated.')) return;
    btnStop.disabled = true;
    btnStop.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Stopping…';
    await apiPost(stopUrl, csrf);
  });

  // ── Status polling ──────────────────────────────────────────────────────
  function updateUI(data) {
    // Badge
    if (statusBadge) {
      statusBadge.textContent  = data.status_label || data.status;
      statusBadge.className    = `badge bg-${data.status_color} fs-6 px-3 py-2`;
    }

    // Packets + duration
    if (packetsEl && data.packets_sent !== undefined)
      packetsEl.textContent = Number(data.packets_sent).toLocaleString();
    if (durationEl && data.duration)
      durationEl.textContent = data.duration;

    // Log tail — only update if content changed (avoid flicker)
    if (logContent && data.log_tail) {
      const trimmed = data.log_tail.trimEnd();
      if (logContent.textContent !== trimmed) {
        logContent.textContent = trimmed;
        if (autoScroll && logContainer)
          logContainer.scrollTop = logContainer.scrollHeight;
      }
    }

    // Error box
    if (data.error) {
      let errBox = document.getElementById('error-box');
      if (!errBox) {
        errBox = document.createElement('div');
        errBox.id = 'error-box';
        errBox.className = 'alert alert-danger mb-4';
        document.getElementById('status-strip')?.after(errBox);
      }
      errBox.innerHTML = `<i class="bi bi-exclamation-triangle me-2"></i><strong>Error:</strong><br><code class="small">${data.error}</code>`;
    }

    // Button state
    const active = data.is_active;
    if (btnStart) btnStart.style.display = active ? 'none' : '';
    if (btnStop)  btnStop.style.display  = active ? '' : 'none';
    if (btnStop)  btnStop.disabled       = (data.status === 'stopping');
  }

  async function poll() {
    try {
      const data = await apiGet(statusUrl);
      updateUI(data);
      if (data.is_active) {
        pollTimeout = setTimeout(poll, 2000);
      } else {
        polling = false;
      }
    } catch {
      // Transient network error — retry
      pollTimeout = setTimeout(poll, 4000);
    }
  }

  function startPolling() {
    if (polling) return;
    polling = true;
    clearTimeout(pollTimeout);
    poll();
  }

  // Auto-start polling if session is currently active
  const activeStatuses = ['starting', 'recording', 'stopping'];
  if (activeStatuses.includes(initialStatus)) {
    startPolling();
    if (logContainer)
      logContainer.scrollTop = logContainer.scrollHeight;
  }
}
