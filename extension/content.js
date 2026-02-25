// content.js — floating HUD overlay on top of Bovada

(function() {
  if (document.getElementById('bj-advisor-hud')) return;

  // ── Build overlay ──────────────────────────────────────────────────────────
  const hud = document.createElement('div');
  hud.id = 'bj-advisor-hud';
  hud.innerHTML = `
    <div id="bj-drag-handle">
      <span id="bj-title">♠ BJ ADVISOR</span>
      <div id="bj-controls">
        <button id="bj-auto-btn" title="Toggle auto-scan">AUTO</button>
        <button id="bj-scan-btn" title="Scan now">SCAN</button>
        <button id="bj-min-btn" title="Minimize">—</button>
      </div>
    </div>
    <div id="bj-body">
      <div id="bj-action-icon">?</div>
      <div id="bj-action-text">WAITING</div>
      <div id="bj-cards-row"></div>
      <div id="bj-info-row"></div>
      <div id="bj-status">Click SCAN or enable AUTO</div>
    </div>
  `;
  document.body.appendChild(hud);

  // ── Drag ──────────────────────────────────────────────────────────────────
  let dx = 0, dy = 0, dragging = false;
  const handle = document.getElementById('bj-drag-handle');
  handle.addEventListener('mousedown', e => {
    dragging = true;
    dx = e.clientX - hud.offsetLeft;
    dy = e.clientY - hud.offsetTop;
    e.preventDefault();
  });
  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    hud.style.left = (e.clientX - dx) + 'px';
    hud.style.top  = (e.clientY - dy) + 'px';
    hud.style.right = 'auto';
  });
  document.addEventListener('mouseup', () => dragging = false);

  // ── Minimize ──────────────────────────────────────────────────────────────
  let minimized = false;
  document.getElementById('bj-min-btn').addEventListener('click', () => {
    minimized = !minimized;
    document.getElementById('bj-body').style.display = minimized ? 'none' : 'flex';
    document.getElementById('bj-min-btn').textContent = minimized ? '+' : '—';
  });

  // ── Scan logic ─────────────────────────────────────────────────────────────
  const STYLES = {
    HIT:       { color: '#00e87a', icon: '↑',  text: 'HIT' },
    STAND:     { color: '#f5c842', icon: '—',  text: 'STAND' },
    DOUBLE:    { color: '#00d4ff', icon: '✦',  text: 'DOUBLE DOWN' },
    SPLIT:     { color: '#b060ff', icon: '⟺', text: 'SPLIT' },
    SURRENDER: { color: '#ff2d55', icon: '✕',  text: 'SURRENDER' },
  };

  function setWaiting(msg) {
    document.getElementById('bj-action-icon').textContent = '?';
    document.getElementById('bj-action-icon').style.color = '#3a3a55';
    document.getElementById('bj-action-text').textContent = 'WAITING';
    document.getElementById('bj-action-text').style.color = '#3a3a55';
    document.getElementById('bj-cards-row').textContent = '';
    document.getElementById('bj-info-row').textContent = '';
    document.getElementById('bj-status').textContent = msg || '';
    hud.style.boxShadow = '0 8px 40px rgba(0,0,0,0.7)';
  }

  function setError(msg) {
    document.getElementById('bj-action-icon').textContent = '✕';
    document.getElementById('bj-action-icon').style.color = '#ff2d55';
    document.getElementById('bj-action-text').textContent = 'ERROR';
    document.getElementById('bj-action-text').style.color = '#ff2d55';
    document.getElementById('bj-status').textContent = msg;
    hud.style.boxShadow = '0 8px 40px rgba(255,45,85,0.3)';
  }

  function setResult(data) {
    if (data.error && !data.action) { setError(data.error); return; }
    if (!data.action) { setWaiting('Cards not visible yet'); return; }

    const s = STYLES[data.action];
    document.getElementById('bj-action-icon').textContent = s.icon;
    document.getElementById('bj-action-icon').style.color = s.color;
    document.getElementById('bj-action-text').textContent = s.text;
    document.getElementById('bj-action-text').style.color = s.color;
    document.getElementById('bj-cards-row').textContent =
      `YOU: ${data.p1} + ${data.p2} (${data.total})   DEALER: ${data.dealer}`;
    document.getElementById('bj-cards-row').style.color = s.color + 'cc';

    let info = '';
    if (data.balance) info += `$${parseFloat(data.balance).toLocaleString()}`;
    if (data.bet)     info += `  BET $${parseFloat(data.bet).toLocaleString()}`;
    document.getElementById('bj-info-row').textContent = info;

    document.getElementById('bj-status').textContent = '✓ ' + new Date().toLocaleTimeString();
    hud.style.boxShadow = `0 8px 40px ${s.color}44`;
  }

  let scanning = false;
  async function doScan() {
    if (scanning) return;
    scanning = true;
    document.getElementById('bj-status').textContent = 'READING TABLE...';
    const result = await chrome.runtime.sendMessage({ type: 'SCAN' });
    setResult(result);
    scanning = false;
  }

  document.getElementById('bj-scan-btn').addEventListener('click', doScan);

  // ── Auto scan ─────────────────────────────────────────────────────────────
  let autoInterval = null;
  const autoBtn = document.getElementById('bj-auto-btn');
  autoBtn.addEventListener('click', () => {
    if (autoInterval) {
      clearInterval(autoInterval);
      autoInterval = null;
      autoBtn.textContent = 'AUTO';
      autoBtn.style.color = '#3a3a55';
      setWaiting('Auto-scan off');
    } else {
      autoBtn.textContent = 'AUTO ●';
      autoBtn.style.color = '#00e87a';
      doScan();
      autoInterval = setInterval(doScan, 4000);
    }
  });

})();
