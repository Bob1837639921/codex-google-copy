const statusText = document.getElementById('status-text');
const indicator = document.getElementById('indicator');
const reconnectButton = document.getElementById('btn-reconnect');
const disconnectButton = document.getElementById('btn-disconnect');

function setStatus(text, state, actions) {
  statusText.textContent = text;
  indicator.className = `indicator${state ? ` ${state}` : ''}`;
  reconnectButton.hidden = !actions.includes('reconnect');
  disconnectButton.hidden = !actions.includes('disconnect');
}

function updateStatus() {
  chrome.runtime.sendMessage({ action: 'getStatus' }, (response) => {
    if (chrome.runtime.lastError || !response) {
      setStatus('扩展后台暂不可用', 'paused', ['reconnect']);
      return;
    }

    if (response.connected) {
      setStatus('已连接本地服务', 'connected', ['disconnect']);
    } else if (response.connecting) {
      setStatus('正在连接本地服务...', 'connecting', []);
    } else if (response.isExplicitlyPaused) {
      setStatus('连接已暂停', 'paused', ['reconnect']);
    } else {
      setStatus('等待网页或本地服务', '', ['reconnect']);
    }
  });
}

reconnectButton.addEventListener('click', () => {
  setStatus('正在连接本地服务...', 'connecting', []);
  chrome.runtime.sendMessage({ action: 'reconnect' }, () => setTimeout(updateStatus, 800));
});

disconnectButton.addEventListener('click', () => {
  setStatus('正在断开连接...', 'connecting', []);
  chrome.runtime.sendMessage({ action: 'disconnect' }, () => setTimeout(updateStatus, 500));
});

updateStatus();
setInterval(updateStatus, 1500);
