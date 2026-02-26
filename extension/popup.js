const keyEl  = document.getElementById('apiKey');
const status = document.getElementById('status');

function show(msg, color) {
  status.textContent = msg;
  status.style.color = color || '#eeeeff';
}

chrome.storage.local.get('apiKey', (res) => {
  if (chrome.runtime.lastError) {
    show('Read error: ' + chrome.runtime.lastError.message, '#ff2d55');
  } else if (res && res.apiKey) {
    keyEl.value = res.apiKey;
    show('✓ Key saved: ' + res.apiKey.slice(0,16) + '...', '#00e87a');
  } else {
    show('Paste your API key above and click Save.', '#55556a');
  }
});

document.getElementById('saveBtn').addEventListener('click', () => {
  const key = keyEl.value.trim();
  if (!key || key.length < 8) { show('Key too short!', '#ff2d55'); return; }
  show('Saving...', '#f5c842');
  chrome.storage.local.set({ apiKey: key }, () => {
    if (chrome.runtime.lastError) {
      show('Error: ' + chrome.runtime.lastError.message, '#ff2d55');
    } else {
      show('✓ SAVED! Go to Bovada and click AUTO.', '#00e87a');
    }
  });
});
