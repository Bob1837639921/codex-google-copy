function updateStatus() {
  chrome.runtime.sendMessage({ action: 'getStatus' }, (response) => {
    if (chrome.runtime.lastError) {
      document.getElementById('status-text').innerText = '未激活 (插件未就绪)';
      document.getElementById('status-text').style.color = '#ef4444';
      document.getElementById('indicator').className = 'indicator paused';
      document.getElementById('btn-reconnect').style.display = 'block';
      return;
    }

    if (!response) return;

    const { connected, connecting, retryCount, isExplicitlyPaused } = response;
    const statusText = document.getElementById('status-text');
    const indicator = document.getElementById('indicator');
    const btnReconnect = document.getElementById('btn-reconnect');

    if (connected) {
      statusText.innerText = '已连接 (服务运行中)';
      statusText.style.color = '#10b981';
      indicator.className = 'indicator connected';
      btnReconnect.style.display = 'none';
    } else if (connecting) {
      statusText.innerText = '正在连接本地服务...';
      statusText.style.color = '#f59e0b';
      indicator.className = 'indicator connecting';
      btnReconnect.style.display = 'none';
    } else if (isExplicitlyPaused) {
      statusText.innerText = '连接失败 (服务未启动/已停止)';
      statusText.style.color = '#ef4444';
      indicator.className = 'indicator paused';
      btnReconnect.style.display = 'block';
      btnReconnect.innerText = '重新连接服务';
    } else {
      statusText.innerText = '静默中 (等待打开任意网页)';
      statusText.style.color = '#94a3b8';
      indicator.className = 'indicator';
      btnReconnect.style.display = 'block';
      btnReconnect.innerText = '强制连接服务';
    }
  });
}

document.getElementById('btn-reconnect').addEventListener('click', () => {
  const statusText = document.getElementById('status-text');
  const indicator = document.getElementById('indicator');
  
  statusText.innerText = '正在尝试连接...';
  statusText.style.color = '#f59e0b';
  indicator.className = 'indicator connecting';
  
  chrome.runtime.sendMessage({ action: 'reconnect' }, () => {
    setTimeout(updateStatus, 1000);
  });
});

// 首次加载和每秒定时刷新状态
updateStatus();
setInterval(updateStatus, 1500);
