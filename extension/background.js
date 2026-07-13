let socket = null;
let agentTabId = null;
let currentGroupId = null;
let sessions = {}; // sessionId -> { tabId, groupId }
let lastErrorLog = [];

let retryCount = 0;
const MAX_RETRIES = 5;
let isExplicitlyPaused = false;
let connectTimeout = null;
const CURSOR_ACTIVE_OPACITY = '1';
const CURSOR_IDLE_OPACITY = '0.62';
const CURSOR_IDLE_DELAY_MS = 8000;
const siteInteractionState = new Map();
const SITE_INTERACTION_POLICIES = [
    {
        name: 'xiaohongshu-strict',
        hostSuffixes: ['xiaohongshu.com'],
        minIntervalMs: 1400,
        maxIntervalMs: 2600,
        settleMinMs: 2500,
        settleMaxMs: 4500,
        actionWindowMs: 60000,
        maxActionsPerWindow: 18
    },
    {
        name: 'alibaba-marketplace-strict',
        hostSuffixes: ['taobao.com', 'tmall.com', 'goofish.com', '1688.com'],
        minIntervalMs: 900,
        maxIntervalMs: 1800,
        settleMinMs: 1800,
        settleMaxMs: 3200,
        actionWindowMs: 60000,
        maxActionsPerWindow: 24
    },
    {
        name: 'jd-marketplace-moderate',
        hostSuffixes: ['jd.com'],
        minIntervalMs: 500,
        maxIntervalMs: 1200,
        settleMinMs: 1000,
        settleMaxMs: 2200,
        actionWindowMs: 60000,
        maxActionsPerWindow: 30
    }
];

function jsString(value) {
  return JSON.stringify(String(value));
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

function randomBetween(min, max) {
    return Math.floor(min + Math.random() * (max - min + 1));
}

function policyForUrl(url) {
    try {
        const hostname = new URL(url).hostname.toLowerCase();
        return SITE_INTERACTION_POLICIES.find(policy => policy.hostSuffixes.some(
            suffix => hostname === suffix || hostname.endsWith(`.${suffix}`)
        )) || null;
    } catch (error) {
        return null;
    }
}

async function policyForTab(tabId, targetUrl = null) {
    if (targetUrl) return policyForUrl(targetUrl);
    const tab = await chrome.tabs.get(tabId);
    return policyForUrl(tab.url || '');
}

async function applySiteInteractionPolicy(tabId, action, targetUrl = null) {
    const policy = await policyForTab(tabId, targetUrl);
    if (!policy) return;

    const now = Date.now();
    let state = siteInteractionState.get(tabId);
    if (!state || state.policyName !== policy.name) {
        state = { policyName: policy.name, lastActionAt: 0, actionTimes: [] };
    }
    state.actionTimes = state.actionTimes.filter(timestamp => now - timestamp < policy.actionWindowMs);
    if (state.actionTimes.length >= policy.maxActionsPerWindow) {
        throw new Error(
            `Site interaction budget reached for ${policy.name}/${action}. Stop, observe the page, and wait before continuing.`
        );
    }

    const requiredInterval = randomBetween(policy.minIntervalMs, policy.maxIntervalMs);
    const elapsed = now - state.lastActionAt;
    if (state.lastActionAt && elapsed < requiredInterval) {
        await sleep(requiredInterval - elapsed);
    }

    const completedAt = Date.now();
    state.lastActionAt = completedAt;
    state.actionTimes.push(completedAt);
    siteInteractionState.set(tabId, state);
}

async function settleAfterNavigation(tabId, targetUrl = null) {
    const policy = await policyForTab(tabId, targetUrl);
    if (!policy) return;
    await sleep(randomBetween(policy.settleMinMs, policy.settleMaxMs));
}

function evaluationNeedsInteractionPacing(code) {
    return /\b(?:scrollBy|scrollTo)\s*\(/.test(String(code || ''));
}

// 每20秒发一次心跳，防止 Chrome 休眠
let keepAliveInterval = setInterval(() => {
    if (socket && socket.readyState === 1 /* WebSocket.OPEN */) {
        socket.send(JSON.stringify({ type: 'ping' }));
    }
}, 20000);

async function triggerConnect(force = false) {
  if (socket && socket.readyState === 1 /* WebSocket.OPEN */) {
    return;
  }
  
  if (force) {
    retryCount = 0;
    isExplicitlyPaused = false;
    if (connectTimeout) {
      clearTimeout(connectTimeout);
      connectTimeout = null;
    }
  }
  
  if (isExplicitlyPaused && !force) {
    console.log('[Connection] Paused due to max retries. Open a website or click popup to retry.');
    return;
  }
  
  connectWebSocket();
}

function connectWebSocket() {
  if (socket && (socket.readyState === 0 || socket.readyState === 1)) {
    return; // Already connecting or connected
  }

  console.log('[Connection] Attempting to connect to bridge server...');
  socket = new WebSocket('ws://localhost:8765');

  socket.onopen = () => {
    console.log('Connected to AI Agent Server');
    retryCount = 0;
    isExplicitlyPaused = false;
    socket.send(JSON.stringify({ type: 'status', message: 'Extension connected' }));
  };

  socket.onmessage = async (event) => {
    const data = JSON.parse(event.data);
    console.log('Received command:', data);

    try {
        const sid = data.sessionId || 'default';
        let tabId = sessions[sid]?.tabId || agentTabId;
        const foreground = sessions[sid]?.foreground === true;

        // 如果断掉或者找不到页面，强行新建页面兜底（仅针对需要 tabId 的页面操控指令）
        const needsTabId = ['navigate', 'reload', 'evaluate', 'hover', 'click', 'type', 'press', 'selectOption', 'snapshot', 'screenshot'];
        if (!tabId && needsTabId.includes(data.action)) {
            await initAgentTab('AI 自动兜底新建', null, sid);
            tabId = sessions[sid].tabId;
        }

        if (foreground && tabId && data.action !== 'init' && data.action !== 'claimTab' && data.action !== 'listTabs' && data.action !== 'getErrorLog' && data.action !== 'testFind') {
            await chrome.tabs.update(tabId, { active: true }).catch(() => {});
        }

        if (data.action === 'init') {
            await initAgentTab(data.taskName || 'AI 正在执行', data.id, data.sessionId);
        } else if (data.action === 'claimTab') {
            await claimAgentTab(data.tabId, data.id, data.sessionId);
        } else if (data.action === 'closeTab') {
            await closeAgentTab(data.tabId ?? tabId, data.id);
        } else if (data.action === 'setVisibility') {
            await setSessionVisibility(sid, data.visible, data.id);
        } else if (data.action === 'ping') {
            socket.send(JSON.stringify({ id: data.id, status: 'success', message: 'Extension connected' }));
        } else if (data.action === 'navigate') {
            await applySiteInteractionPolicy(tabId, 'navigate', data.url);
            await executeNavigate(tabId, data.url, data.id, foreground);
        } else if (data.action === 'reload') {
            await applySiteInteractionPolicy(tabId, 'reload');
            await executeReload(tabId, data.id);
        } else if (data.action === 'evaluate') {
            if (evaluationNeedsInteractionPacing(data.code)) {
                await applySiteInteractionPolicy(tabId, 'scroll');
            }
            await executeEvaluate(tabId, data.code, data.id);
        } else if (data.action === 'hover') {
            await applySiteInteractionPolicy(tabId, 'hover');
            await executeHover(tabId, data.selector, data.id);
        } else if (data.action === 'click') {
            await applySiteInteractionPolicy(tabId, 'click');
            await executeClick(tabId, data.selector, data.mode, data.id);
        } else if (data.action === 'type') {
            await applySiteInteractionPolicy(tabId, 'type');
            await executeType(tabId, data.selector, data.text, data.mode, data.submit !== false, data.id);
        } else if (data.action === 'press') {
            await applySiteInteractionPolicy(tabId, 'press');
            await executePress(tabId, data.key, data.id);
        } else if (data.action === 'selectOption') {
            await applySiteInteractionPolicy(tabId, 'selectOption');
            await executeSelectOption(tabId, data.selector, data, data.id);
        } else if (data.action === 'snapshot') {
            await executeSnapshot(tabId, data.id);
        } else if (data.action === 'screenshot') {
            await executeScreenshot(tabId, data.id, data.fullPage);
        } else if (data.action === 'download') {
            await executeDownload(data.url, data.filename, data.id);
        } else if (data.action === 'searchDownloads') {
            await executeSearchDownloads(data.query, data.id);
        } else if (data.action === 'fetchAsBase64') {
            await executeFetchAsBase64(data.url, data.id);
        } else if (data.action === 'downloadViaBlob') {
            await executeDownloadViaBlob(data.url, data.filename, data.id);
        } else if (data.action === 'listTabs') {
            const tabs = await chrome.tabs.query({});
            const resTabs = tabs.map(t => ({ id: t.id, url: t.url, title: t.title, active: t.active, windowId: t.windowId }));
            socket.send(JSON.stringify({ id: data.id, status: 'success', result: resTabs }));
        } else if (data.action === 'getErrorLog') {
            socket.send(JSON.stringify({ id: data.id, status: 'success', result: lastErrorLog }));
        } else if (data.action === 'testFind') {
            const tabs = await chrome.tabs.query({});
            const chatgptTab = tabs.find(t => t.url && t.url.includes('chatgpt.com'));
            socket.send(JSON.stringify({ id: data.id, status: 'success', result: {
                tabsCount: tabs.length,
                chatgptFound: !!chatgptTab,
                chatgptUrl: chatgptTab ? chatgptTab.url : null,
                urls: tabs.map(t => t.url)
            }}));
        } else if (data.action === 'evalBg') {
            try {
                // Use function constructor to run in global context
                const fn = new Function('return (async () => { ' + data.code + ' })()');
                const evalResult = await fn();
                socket.send(JSON.stringify({ id: data.id, status: 'success', result: evalResult }));
            } catch (err) {
                socket.send(JSON.stringify({ id: data.id, status: 'error', error: err.toString() }));
            }
        } else if (data.action === 'screenshotActiveTab') {
            const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tabs.length > 0) {
                const activeTabId = tabs[0].id;
                await attachDebugger(activeTabId);
                await executeScreenshot(activeTabId, data.id, data.fullPage);
            } else {
                socket.send(JSON.stringify({ id: data.id, status: 'error', error: 'No active tab found' }));
            }
        } else if (data.action === 'getActiveTab') {
            const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
            if (tabs.length > 0) {
                socket.send(JSON.stringify({ id: data.id, status: 'success', tab: { id: tabs[0].id, url: tabs[0].url, title: tabs[0].title } }));
            } else {
                socket.send(JSON.stringify({ id: data.id, status: 'error', error: 'No active tab found' }));
            }
        }
    } catch (e) {
        socket.send(JSON.stringify({ id: data.id, status: 'error', error: e.toString() }));
    }
  };

  socket.onclose = () => {
    console.log('WebSocket closed.');
    if (agentTabId) {
        sendCommand(agentTabId, 'Runtime.evaluate', {
            expression: `
                const cursor = document.getElementById('ai-fake-cursor');
                if (cursor) {
                    cursor.style.opacity = '0';
                }
            `
        }).catch(() => {});
    }
    socket = null;
    handleReconnect();
  };
  
  socket.onerror = (error) => {
    console.log('WebSocket Error:', error);
  };
}

function handleReconnect() {
  if (isExplicitlyPaused) return;

  retryCount++;
  if (retryCount > MAX_RETRIES) {
    isExplicitlyPaused = true;
    console.log('[Connection] Maximum retry limit reached. Connection attempts paused.');
    return;
  }

  // 指数退避：3s, 6s, 12s, 24s, 30s
  const delay = Math.min(3000 * Math.pow(2, retryCount - 1), 30000);
  console.log(`[Connection] Reconnecting in ${delay / 1000}s (Attempt ${retryCount}/${MAX_RETRIES})...`);
  
  if (connectTimeout) clearTimeout(connectTimeout);
  connectTimeout = setTimeout(() => {
    triggerConnect();
  }, delay);
}

// 监听标签页更新与激活事件，随时自动唤醒连接并管理鼠标隐藏
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
    console.log('[Event] HTTP/HTTPS tab updated, triggering reconnect check...');
    triggerConnect(true);
  }
  // 核心：若接管的代理标签页发生了重载、刷新或单页应用（SPA）历史路由变更，强制瞬间隐藏鼠标！
  if (tabId === agentTabId && (changeInfo.status === 'complete' || changeInfo.url)) {
    chrome.debugger.sendCommand({ tabId: agentTabId }, 'Runtime.evaluate', {
      expression: `
        const cursor = document.getElementById('ai-fake-cursor');
        if (cursor) {
            cursor.style.opacity = '${CURSOR_IDLE_OPACITY}';
        }
      `
    }).catch(() => {});
  }
});

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    if (tab.url && (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
      console.log('[Event] HTTP/HTTPS tab activated, triggering reconnect check...');
      triggerConnect(true);
    }
  } catch (e) {}
});

// 监听标签页手动关闭事件，及时同步状态
chrome.tabs.onRemoved.addListener((tabId) => {
  siteInteractionState.delete(tabId);
  if (tabId === agentTabId) {
    agentTabId = null;
    currentGroupId = null;
  }
  for (const sid in sessions) {
    if (sessions[sid].tabId === tabId) {
      delete sessions[sid];
    }
  }
});

// 处理来自 Popup 的状态查询和重连指令
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getStatus') {
    const isConnected = socket && socket.readyState === 1;
    const isConnecting = socket && socket.readyState === 0;
    sendResponse({
      connected: isConnected,
      connecting: isConnecting,
      retryCount: retryCount,
      isExplicitlyPaused: isExplicitlyPaused
    });
  } else if (request.action === 'reconnect') {
    triggerConnect(true);
    sendResponse({ status: 'connecting' });
  } else if (request.action === 'disconnect') {
    isExplicitlyPaused = true;
    if (socket) {
      socket.close();
    }
    if (connectTimeout) {
      clearTimeout(connectTimeout);
      connectTimeout = null;
    }
    sendResponse({ status: 'disconnected' });
  }
  return true; // Keep message channel open for async response
});


async function initAgentTab(taskName, msgId, sessionId) {
    // 默认会话 ID 设为 'default'，如果用户指定了会话（如不同的对话），则隔离管理
    const sid = sessionId || 'default';
    
    // 如果此会话已经有开启的标签页，检查是否仍然存在。若存在则直接复用，避免重复关闭创建
    if (sessions[sid]) {
        try {
            const oldTabId = sessions[sid].tabId;
            const tab = await chrome.tabs.get(oldTabId);
            if (tab) {
                agentTabId = oldTabId;
                currentGroupId = sessions[sid].groupId;
                await chrome.tabGroups.update(currentGroupId, {
                    title: taskName,
                    color: 'cyan'
                });
                await attachDebugger(agentTabId);
                if (msgId) {
                    socket.send(JSON.stringify({ id: msgId, status: 'success', message: 'Tab reused' }));
                }
                return;
            }
        } catch (e) {
            // 忽略找不到或者获取失败的情况，代表老标签页已被手动关闭
            delete sessions[sid];
        }
    }

    const tab = await chrome.tabs.create({ url: 'about:blank', active: false });
    agentTabId = tab.id;
    
    currentGroupId = await chrome.tabs.group({ tabIds: [agentTabId] });
    await chrome.tabGroups.update(currentGroupId, { 
        title: taskName, 
        color: 'cyan'
    });
    
    await attachDebugger(agentTabId);
    
    // 将新建标签页记录到会话列表中
    sessions[sid] = {
        tabId: agentTabId,
        groupId: currentGroupId,
        foreground: false
    };
    
    if (msgId) {
        socket.send(JSON.stringify({ id: msgId, status: 'success', message: 'Tab created and grouped' }));
    }
}

async function claimAgentTab(tabId, msgId, sessionId) {
    const sid = sessionId || 'default';
    if (!Number.isInteger(tabId)) {
        throw new Error('claimTab requires a numeric tabId returned by listTabs');
    }
    const tab = await chrome.tabs.get(tabId);
    if (!tab.url || (!tab.url.startsWith('http://') && !tab.url.startsWith('https://'))) {
        throw new Error('Only HTTP/HTTPS tabs can be claimed');
    }
    await attachDebugger(tabId);
    agentTabId = tabId;
    currentGroupId = tab.groupId >= 0 ? tab.groupId : null;
    sessions[sid] = { tabId, groupId: currentGroupId, foreground: false };
    socket.send(JSON.stringify({
        id: msgId,
        status: 'success',
        tab: { id: tab.id, url: tab.url, title: tab.title, windowId: tab.windowId }
    }));
}

async function setSessionVisibility(sessionId, visible, msgId) {
    const session = sessions[sessionId];
    if (!session) {
        throw new Error('Initialize or claim a tab before changing visibility');
    }
    session.foreground = visible === true;
    if (session.foreground) {
        await chrome.tabs.update(session.tabId, { active: true });
    }
    socket.send(JSON.stringify({
        id: msgId,
        status: 'success',
        visible: session.foreground,
        tabId: session.tabId
    }));
}

async function closeAgentTab(tabId, msgId) {
    if (!Number.isInteger(tabId)) {
        throw new Error('closeTab requires a numeric tabId or an initialized session');
    }
    const tab = await chrome.tabs.get(tabId);
    await chrome.tabs.remove(tabId);

    for (const [sid, session] of Object.entries(sessions)) {
        if (session.tabId === tabId) delete sessions[sid];
    }
    if (agentTabId === tabId) agentTabId = null;

    socket.send(JSON.stringify({
        id: msgId,
        status: 'success',
        closedTab: { id: tab.id, url: tab.url, title: tab.title }
    }));
}

async function attachDebugger(tabId) {
  return new Promise((resolve, reject) => {
    chrome.debugger.getTargets((targets) => {
      let isAttached = false;
      for (let target of targets) {
        if (target.tabId === tabId && target.attached) {
          isAttached = true;
          break;
        }
      }
      if (isAttached) {
        resolve();
      } else {
        chrome.debugger.attach({ tabId: tabId }, "1.3", () => {
          if (chrome.runtime.lastError) {
            reject(chrome.runtime.lastError.message);
          } else {
            resolve();
          }
        });
      }
    });
  });
}

async function sendCommand(tabId, method, params = {}, timeoutMs = 30000) {
  const invoke = () => new Promise((resolve, reject) => {
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      callback(value);
    };
    const timer = setTimeout(() => {
      finish(reject, new Error(`CDP command ${method} timed out for tab ${tabId}`));
    }, timeoutMs);

    chrome.debugger.sendCommand({ tabId }, method, params, (result) => {
      const errMsg = chrome.runtime.lastError?.message;
      if (errMsg) {
        finish(reject, new Error(errMsg));
      } else {
        finish(resolve, result);
      }
    });
  });

  try {
    return await invoke();
  } catch (error) {
    const errMsg = error?.message || String(error);
    const detached = errMsg.includes("Debugger is not attached") || errMsg.includes("not attached to the tab");
    if (!detached) throw error;

    console.warn(`[Debugger] Detached detected. Attempting to auto re-attach to tab ${tabId}...`);
    try {
      await attachDebugger(tabId);
      return await invoke();
    } catch (attachErr) {
      throw new Error(`Failed to re-attach debugger: ${attachErr}. Original error: ${errMsg}`);
    }
  }
}

async function ensureAgentTab() {
    if (agentTabId) {
        try {
            await chrome.tabs.get(agentTabId);
            return;
        } catch (e) {
            agentTabId = null;
        }
    }
    
    // 如果插件重启丢失了 agentTabId，直接接管当前用户正在看的标签页！
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs.length > 0) {
        agentTabId = tabs[0].id;
        try {
            await attachDebugger(agentTabId);
            // 接管后，把它放进一个标签组，打上醒目的标签
            currentGroupId = await chrome.tabs.group({ tabIds: [agentTabId] });
            await chrome.tabGroups.update(currentGroupId, { 
                title: 'AI 接管执行中', 
                color: 'cyan'
            });
        } catch(e) {}
    } else {
        await initAgentTab('AI 正在接管');
    }
}

async function ensureFakeCursor(tabId) {
    const code = `
        if (!document.getElementById('ai-fake-cursor')) {
            const cursor = document.createElement('div');
            cursor.id = 'ai-fake-cursor';
            cursor.style.position = 'fixed';
            cursor.style.zIndex = '2147483647';
            cursor.style.pointerEvents = 'none';
            cursor.style.width = '34px';
            cursor.style.height = '34px';
            cursor.style.background = 'url("data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'34\\' height=\\'34\\' viewBox=\\'0 0 24 24\\' fill=\\'%23FF3366\\' stroke=\\'white\\' stroke-width=\\'1.7\\' stroke-linecap=\\'round\\' stroke-linejoin=\\'round\\'%3E%3Cpolygon points=\\'3 3 10 21 14 14 21 10 3 3\\'%3E%3C/polygon%3E%3C/svg%3E") no-repeat';
            cursor.style.backgroundSize = 'contain';
            cursor.style.transition = 'top 0.55s cubic-bezier(.2,.8,.2,1), left 0.55s cubic-bezier(.2,.8,.2,1), opacity 0.25s ease, transform 0.16s ease, filter 0.2s ease';
            cursor.style.opacity = '${CURSOR_IDLE_OPACITY}';
            cursor.style.top = '18px';
            cursor.style.left = '18px';
            cursor.style.transformOrigin = '4px 4px';
            cursor.style.filter = 'drop-shadow(0 5px 10px rgba(0,0,0,0.32)) drop-shadow(0 0 10px rgba(255,51,102,0.38))';
            document.body.appendChild(cursor);
        }

        window.__ai_cursor_keep_visible = () => {
            const cursor = document.getElementById('ai-fake-cursor');
            if (!cursor) return;
            if (window.__ai_cursor_hide_timeout) {
                clearTimeout(window.__ai_cursor_hide_timeout);
            }
            cursor.style.opacity = '${CURSOR_ACTIVE_OPACITY}';
            window.__ai_cursor_hide_timeout = setTimeout(() => {
                const cur = document.getElementById('ai-fake-cursor');
                if (cur) cur.style.opacity = '${CURSOR_IDLE_OPACITY}';
            }, ${CURSOR_IDLE_DELAY_MS});
        };

        window.__ai_cursor_move_to = (x, y) => {
            const cursor = document.getElementById('ai-fake-cursor');
            if (!cursor) return;
            cursor.style.left = Math.round(x) + 'px';
            cursor.style.top = Math.round(y) + 'px';
            window.__ai_cursor_keep_visible();
        };

        window.__ai_cursor_pulse = () => {
            const cursor = document.getElementById('ai-fake-cursor');
            if (!cursor) return;
            window.__ai_cursor_keep_visible();
            cursor.style.transform = 'scale(0.78)';
            cursor.style.filter = 'drop-shadow(0 5px 10px rgba(0,0,0,0.34)) drop-shadow(0 0 18px rgba(255,51,102,0.85))';
            setTimeout(() => {
                const cur = document.getElementById('ai-fake-cursor');
                if (cur) {
                    cur.style.transform = 'scale(1)';
                    cur.style.filter = 'drop-shadow(0 5px 10px rgba(0,0,0,0.32)) drop-shadow(0 0 10px rgba(255,51,102,0.38))';
                }
            }, 160);
        };

        window.__ai_cursor_keep_visible();
    `;
    await sendCommand(tabId, 'Runtime.evaluate', { expression: code });
}

async function touchFakeCursor(tabId) {
    await ensureFakeCursor(tabId);
    await sendCommand(tabId, 'Runtime.evaluate', {
        expression: `
            (() => {
                if (window.__ai_cursor_keep_visible) {
                    window.__ai_cursor_keep_visible();
                }
                return true;
            })();
        `
    }).catch(() => {});
}

async function executeNavigate(tabId, url, msgId, foreground = false) {
  await chrome.tabs.update(tabId, { url: url, active: foreground });
  await waitForTabComplete(tabId);
  await settleAfterNavigation(tabId, url);
  await ensureFakeCursor(tabId);
  const tab = await chrome.tabs.get(tabId);
  socket.send(JSON.stringify({
      id: msgId,
      status: 'success',
      tab: { id: tab.id, url: tab.url, title: tab.title }
  }));
}

async function executeReload(tabId, msgId) {
  await chrome.tabs.reload(tabId);
  await waitForTabComplete(tabId);
  await settleAfterNavigation(tabId);
  await ensureFakeCursor(tabId);
  const tab = await chrome.tabs.get(tabId);
  socket.send(JSON.stringify({
      id: msgId,
      status: 'success',
      tab: { id: tab.id, url: tab.url, title: tab.title }
  }));
}

async function waitForTabComplete(tabId, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
      const tab = await chrome.tabs.get(tabId);
      if (tab.status === 'complete') return tab;
      await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error(`Timed out waiting for tab ${tabId} to finish loading`);
}

async function executeEvaluate(tabId, code, msgId) {
  await touchFakeCursor(tabId);
  const result = await sendCommand(tabId, 'Runtime.evaluate', {
    expression: code,
    returnByValue: true,
    awaitPromise: true
  });

  if (result.exceptionDetails) {
    const details = result.exceptionDetails;
    const description = details.exception?.description || details.text || 'Unknown page evaluation error';
    throw new Error(description);
  }
  if (result.result?.subtype === 'error') {
    throw new Error(result.result.description || 'Page evaluation returned an error');
  }
  socket.send(JSON.stringify({ id: msgId, status: 'success', result: result.result?.value }));
}

async function executeHover(tabId, selector, msgId) {
    await ensureFakeCursor(tabId);
    const selectorLiteral = jsString(selector);
    const codeMove = `
        (() => {
            const el = document.querySelector(${selectorLiteral});
            if (!el) return false;
            
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            setTimeout(() => {
                const rect = el.getBoundingClientRect();
                const cursor = document.getElementById('ai-fake-cursor');
                if (cursor) {
                    if (window.__ai_cursor_hide_timeout) {
                        clearTimeout(window.__ai_cursor_hide_timeout);
                    }
                    
                    cursor.style.opacity = '${CURSOR_ACTIVE_OPACITY}';
                    cursor.style.left = (rect.left + rect.width / 2) + 'px';
                    cursor.style.top = (rect.top + rect.height / 2) + 'px';
                    
                    window.__ai_cursor_hide_timeout = setTimeout(() => {
                        const cur = document.getElementById('ai-fake-cursor');
                        if (cur) cur.style.opacity = '${CURSOR_IDLE_OPACITY}';
                    }, ${CURSOR_IDLE_DELAY_MS});
                }
            }, 300);
            return true;
        })();
    `;
    const moveResult = await sendCommand(tabId, 'Runtime.evaluate', { expression: codeMove, returnByValue: true });
    const moved = moveResult.result?.value;
    if (!moved) {
        if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'error', error: `Element not found for selector: ${selector}` }));
        return false;
    }
    
    setTimeout(() => {
        if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'success' }));
    }, 1200); 
    return true;
}

async function executeClick(tabId, selector, modeOrMsgId, msgId) {
    let mode = 'smart';
    let actualMsgId = msgId || modeOrMsgId;
    if (typeof modeOrMsgId === 'string' && modeOrMsgId !== 'null' && modeOrMsgId.length < 10) {
        mode = modeOrMsgId;
    }

    const moved = await executeHover(tabId, selector, null); 
    if (!moved) {
        if(actualMsgId) socket.send(JSON.stringify({ id: actualMsgId, status: 'error', error: `Element not found for selector: ${selector}` }));
        return;
    }
    const selectorLiteral = jsString(selector);
    const modeLiteral = jsString(mode);
    
    setTimeout(async () => {
        try {
            const codeClick = `
                (async () => {
                    const el = document.querySelector(${selectorLiteral});
                    if (el) { 
                        const cursor = document.getElementById('ai-fake-cursor');
                        if (cursor && window.__ai_cursor_pulse) {
                            window.__ai_cursor_pulse();
                        }
                        const runMode = ${modeLiteral};
                        await new Promise(resolve => setTimeout(resolve, 50));
                        if (runMode === 'direct') {
                            el.click();
                        } else {
                            const opts = { bubbles: true, cancelable: true, view: window };
                            el.dispatchEvent(new PointerEvent('pointerdown', opts));
                            el.dispatchEvent(new MouseEvent('mousedown', opts));
                            if (typeof el.focus === 'function') el.focus();
                            el.dispatchEvent(new PointerEvent('pointerup', opts));
                            el.dispatchEvent(new MouseEvent('mouseup', opts));
                            el.click();
                        }
                        return true; 
                    }
                    return false;
                })();
            `;
            const clickResult = await sendCommand(tabId, 'Runtime.evaluate', {
                expression: codeClick,
                returnByValue: true,
                awaitPromise: true
            });
            if (!clickResult.result?.value) {
                if(actualMsgId) socket.send(JSON.stringify({ id: actualMsgId, status: 'error', error: `Element not found for selector: ${selector}` }));
                return;
            }
            if(actualMsgId) socket.send(JSON.stringify({ id: actualMsgId, status: 'success' }));
        } catch (e) {
            console.error("Error in executeClick timeout:", e);
            if(actualMsgId) socket.send(JSON.stringify({ id: actualMsgId, status: 'error', error: e.toString() }));
        }
    }, 1200); 
}

async function executeType(tabId, selector, text, mode, submit, msgId) {
    const isDirect = (mode === 'direct');
    const moved = await executeHover(tabId, selector, null);
    if (!moved) {
        if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'error', error: `Element not found for selector: ${selector}` }));
        return;
    }
    const selectorLiteral = jsString(selector);
    const textLiteral = jsString(text);
    
    setTimeout(async () => {
        try {
            const codeClick = `
                (async () => {
                    const el = document.querySelector(${selectorLiteral});
                    if (el) { 
                        el.focus();
                        el.click();
                        if (el.tagName === 'DIV' || el.contentEditable === 'true') {
                            el.innerHTML = '';
                            const fullText = ${textLiteral};
                            if (${isDirect}) {
                                document.execCommand('insertText', false, fullText);
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                return "direct_success";
                            }
                            for (const char of fullText) {
                                document.execCommand('insertText', false, char);
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                await new Promise(r => setTimeout(r, Math.random() * 80 + 50));
                            }
                            return "exec_success";
                        }
                        const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(proto, "value").set;
                        if (${isDirect}) {
                            if (nativeInputValueSetter) {
                                nativeInputValueSetter.call(el, ${textLiteral});
                            } else {
                                el.value = ${textLiteral};
                            }
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            return "direct_success";
                        }
                        if (nativeInputValueSetter) {
                            nativeInputValueSetter.call(el, '');
                        } else {
                            el.value = '';
                        }
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        return "standard_input";
                    }
                    return "not_found";
                })()
            `;
            const res = await sendCommand(tabId, 'Runtime.evaluate', { 
                expression: codeClick, 
                returnByValue: true,
                awaitPromise: true 
            });
            const typeMode = res.result?.value;
            if (typeMode === "not_found") {
                if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'error', error: `Element not found for selector: ${selector}` }));
                return;
            }
            
            if (typeMode === "standard_input") {
                for (const char of text) {
                    await sendCommand(tabId, 'Input.insertText', { text: char });
                    const delay = Math.floor(Math.random() * 80) + 50;
                    await new Promise(resolve => setTimeout(resolve, delay));
                }
            }
            
            if (submit) {
                await sendCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
                await sendCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
            }
 
            if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'success' }));
        } catch (e) {
            console.error("Error in executeType timeout:", e);
            if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'error', error: e.toString() }));
        }
    }, 1200);
}

async function executePress(tabId, key, msgId) {
    if (!key || typeof key !== 'string') {
        socket.send(JSON.stringify({ id: msgId, status: 'error', error: 'A non-empty key is required' }));
        return;
    }
    const parts = key.split('+').map(part => part.trim()).filter(Boolean);
    const keyName = parts.pop();
    const modifiers = parts.reduce((mask, modifier) => {
        const normalized = modifier.toLowerCase();
        if (normalized === 'alt') return mask | 1;
        if (normalized === 'control' || normalized === 'ctrl') return mask | 2;
        if (normalized === 'meta' || normalized === 'command') return mask | 4;
        if (normalized === 'shift') return mask | 8;
        return mask;
    }, 0);
    await sendCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', key: keyName, code: keyName, modifiers });
    await sendCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', key: keyName, code: keyName, modifiers });
    socket.send(JSON.stringify({ id: msgId, status: 'success', key }));
}

async function executeSelectOption(tabId, selector, options, msgId) {
    const expression = `
        (() => {
            const el = document.querySelector(${jsString(selector)});
            if (!el) return { ok: false, error: 'element_not_found' };
            if (el.tagName !== 'SELECT') return { ok: false, error: 'element_is_not_select' };
            const choices = Array.from(el.options);
            let option = null;
            if (${JSON.stringify(options.value ?? null)} !== null) {
                option = choices.find(item => item.value === ${JSON.stringify(options.value ?? null)});
            } else if (${JSON.stringify(options.label ?? null)} !== null) {
                option = choices.find(item => item.label === ${JSON.stringify(options.label ?? null)} || item.text === ${JSON.stringify(options.label ?? null)});
            } else if (${JSON.stringify(options.index ?? null)} !== null) {
                option = choices[Number(${JSON.stringify(options.index ?? null)})] || null;
            }
            if (!option) return { ok: false, error: 'option_not_found' };
            el.value = option.value;
            option.selected = true;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return { ok: true, value: option.value, label: option.label || option.text, index: option.index };
        })()
    `;
    const result = await sendCommand(tabId, 'Runtime.evaluate', { expression, returnByValue: true });
    const value = result.result?.value;
    if (!value?.ok) {
        socket.send(JSON.stringify({ id: msgId, status: 'error', error: value?.error || 'Could not select option' }));
        return;
    }
    socket.send(JSON.stringify({ id: msgId, status: 'success', result: value }));
}

async function executeSnapshot(tabId, msgId) {
    await touchFakeCursor(tabId);
    const code = `
        (() => {
            const contentSelectors = [
                '.comments-container', '.comment-list', '.comment-item', '.comment-inner-container',
                '#detail-desc', '.desc-container', '.note-text', '.note-title',
                '.feed-card', '.feeds-container', '#reviews', '#comments', '.comment-area'
            ];
            
            const isInsideExcludedContent = (el) => {
                if (!el) return false;
                try {
                    return !!el.closest(contentSelectors.join(','));
                } catch(e) {
                    return false;
                }
            };

            const bodyText = (() => {
                try {
                    const bodyClone = document.body.cloneNode(true);
                    contentSelectors.forEach(sel => {
                        bodyClone.querySelectorAll(sel).forEach(el => el.remove());
                    });
                    return bodyClone.innerText || '';
                } catch(e) {
                    return document.body.innerText || '';
                }
            })();

            const loginSelectors = [
                '.login-box',
                '#login-box',
                '.suplogin',
                'input[type="password"]',
                'form[action*="login"]',
                '[class*="passport"]',
                '[id*="passport"]',
                '[class*="captcha"]',
                '[id*="captcha"]'
            ];
            const loginKeywords = [
                '密码登录',
                '短信登录',
                '扫码登录',
                '安全验证',
                '滑块验证',
                '验证码',
                'captcha',
                'security verification'
            ];
            const riskKeywords = [
                '访问频繁',
                '操作频繁',
                '请求频繁',
                '当前访问存在异常',
                '页面访问异常',
                '网络环境存在风险',
                '账号存在风险',
                '异常请求',
                '请稍后重试',
                'too many requests',
                'unusual traffic',
                'access denied'
            ];
            const hasLogin = loginSelectors.some((selector) => {
                                const el = document.querySelector(selector);
                                if (!el) return false;
                                if (isInsideExcludedContent(el)) return false;
                                const rect = el.getBoundingClientRect();
                                const style = window.getComputedStyle(el);
                                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                            }) ||
                            loginKeywords.some((keyword) => bodyText.toLowerCase().includes(keyword.toLowerCase())) ||
                            window.location.href.includes('login.taobao.com') ||
                            window.location.href.includes('passport');
            const matchedRiskKeyword = riskKeywords.find(
                keyword => bodyText.toLowerCase().includes(keyword.toLowerCase())
            ) || null;
            
            function getCleanText(el) {
                return el.innerText ? el.innerText.trim().replace(/\\s+/g, ' ') : '';
            }
            const elements = Array.from(document.querySelectorAll('a, button, input, h1, h2, h3, .price, .title'));
            const items = elements.map(el => {
                const tag = el.tagName.toLowerCase();
                const text = tag === 'input' ? (el.value || el.placeholder || el.name) : getCleanText(el);
                const className = el.className && typeof el.className === 'string' ? el.className.trim() : '';
                const id = el.id ? '#' + el.id : '';
                const classSelector = className ? '.' + className.split(/\\s+/).join('.') : '';
                return tag + id + classSelector + ' | text: ' + text;
            }).filter(item => item.length > 5 && !item.endsWith(': '));
            
            return {
                blockedByLogin: hasLogin,
                blockedByRisk: Boolean(matchedRiskKeyword),
                blockerReason: matchedRiskKeyword,
                dom: Array.from(new Set(items)).slice(0, 80)
            };
        })();
    `;
    const result = await sendCommand(tabId, 'Runtime.evaluate', { expression: code, returnByValue: true });
    const data = result.result?.value || { blockedByLogin: false, blockedByRisk: false, blockerReason: null, dom: [] };
    socket.send(JSON.stringify({ 
        id: msgId, 
        status: 'success', 
        blockedByLogin: data.blockedByLogin,
        blockedByRisk: data.blockedByRisk,
        blockerReason: data.blockerReason,
        dom: data.dom 
    }));
}

async function executeScreenshot(tabId, msgId, fullPage = false) {
    await touchFakeCursor(tabId);
    try {
        await sendCommand(tabId, 'Page.enable');
        let params = {
            format: 'png',
            fromSurface: true,
            captureBeyondViewport: !!fullPage
        };

        if (fullPage) {
            const metrics = await sendCommand(tabId, 'Page.getLayoutMetrics');
            const contentSize = metrics.contentSize;
            if (contentSize && contentSize.width && contentSize.height) {
                params.clip = {
                    x: 0,
                    y: 0,
                    width: Math.ceil(contentSize.width),
                    height: Math.ceil(contentSize.height),
                    scale: 1
                };
            }
        }

        const result = await sendCommand(tabId, 'Page.captureScreenshot', params);
        socket.send(JSON.stringify({
            id: msgId,
            status: 'success',
            mime: 'image/png',
            base64: result.data,
            fullPage: !!fullPage
        }));
    } catch (e) {
        socket.send(JSON.stringify({ id: msgId, status: 'error', error: e.toString() }));
    }
}

async function executeDownload(url, filename, msgId) {
    chrome.downloads.download({
        url: url,
        filename: filename,
        conflictAction: 'overwrite',
        saveAs: false
    }, (downloadId) => {
        if (chrome.runtime.lastError) {
            socket.send(JSON.stringify({ id: msgId, status: 'error', error: chrome.runtime.lastError.message }));
        } else {
            socket.send(JSON.stringify({ id: msgId, status: 'success', downloadId: downloadId }));
        }
    });
}

async function executeSearchDownloads(query, msgId) {
    chrome.downloads.search(query || {}, (results) => {
        if (chrome.runtime.lastError) {
            socket.send(JSON.stringify({ id: msgId, status: 'error', error: chrome.runtime.lastError.message }));
        } else {
            socket.send(JSON.stringify({ id: msgId, status: 'success', results: results }));
        }
    });
}

// Fetch a URL using the extension's authenticated cookie context and return it as base64.
// Only suitable for IMAGE files under 30MB. For other file types or larger files,
// use chrome.downloads.download() instead.
async function executeFetchAsBase64(url, msgId) {
    const MAX_SIZE_BYTES = 30 * 1024 * 1024; // 30MB 上限
    const ALLOWED_MIME_PREFIXES = ['image/'];  // 仅允许图片类型

    try {
        // 先发 HEAD 请求检查文件类型和大小，避免下载大文件后再拒绝
        let mime = null;
        let contentLength = null;
        try {
            const headRes = await fetch(url, {
                method: 'HEAD',
                credentials: 'include',
                cache: 'no-store'
            });
            mime = headRes.headers.get('content-type') || '';
            contentLength = parseInt(headRes.headers.get('content-length') || '0', 10);
        } catch (_) {
            // 部分服务器不支持 HEAD，跳过预检，继续尝试 GET
        }

        // 文件类型检查（仅在 HEAD 成功拿到 MIME 时校验）
        const isChatGPTFile = url.includes('/estuary/content') || url.includes('/backend-api/files') || url.includes('files.oaiusercontent.com');
        if (mime && !isChatGPTFile && !ALLOWED_MIME_PREFIXES.some(prefix => mime.startsWith(prefix))) {
            socket.send(JSON.stringify({
                id: msgId,
                status: 'error',
                reason: 'unsupported_mime',
                error: `fetchAsBase64 仅支持图片文件（image/*），当前类型为 "${mime}"。请改用 chrome.downloads.download() 下载此类型文件。`
            }));
            return;
        }

        // 文件大小检查（仅在 HEAD 成功拿到 Content-Length 时校验）
        if (contentLength && contentLength > MAX_SIZE_BYTES) {
            socket.send(JSON.stringify({
                id: msgId,
                status: 'error',
                reason: 'file_too_large',
                error: `fetchAsBase64 仅支持 30MB 以内的文件，当前文件约 ${(contentLength / 1024 / 1024).toFixed(1)}MB。请改用 chrome.downloads.download() 下载大文件。`
            }));
            return;
        }

        // 正式 GET 请求
        const response = await fetch(url, {
            credentials: 'include',
            cache: 'no-store'
        });
        if (!response.ok) {
            socket.send(JSON.stringify({
                id: msgId,
                status: 'error',
                error: `HTTP ${response.status}: ${response.statusText}`
            }));
            return;
        }

        const buffer = await response.arrayBuffer();
        const uint8 = new Uint8Array(buffer);

        // 双重大小兜底（HEAD 可能拿不到 Content-Length）
        if (uint8.length > MAX_SIZE_BYTES) {
            socket.send(JSON.stringify({
                id: msgId,
                status: 'error',
                reason: 'file_too_large',
                error: `fetchAsBase64 仅支持 30MB 以内的文件，实际大小 ${(uint8.length / 1024 / 1024).toFixed(1)}MB。请改用 chrome.downloads.download() 下载大文件。`
            }));
            return;
        }

        // 转 base64（分块处理，避免大文件栈溢出）
        let binary = '';
        const chunkSize = 8192;
        for (let i = 0; i < uint8.length; i += chunkSize) {
            binary += String.fromCharCode(...uint8.subarray(i, i + chunkSize));
        }
        const base64 = btoa(binary);
        const actualMime = response.headers.get('content-type') || mime || 'image/png';

        socket.send(JSON.stringify({
            id: msgId,
            status: 'success',
            base64: base64,
            mime: actualMime,
            size: uint8.length
        }));
    } catch (e) {
        socket.send(JSON.stringify({ id: msgId, status: 'error', error: e.toString() }));
    }
}


// 通过 Service Worker 带 Cookie fetch 任意 URL → 转成 blob: URL → chrome.downloads 下载。
// blob: URL 不会被第三方下载管理器（FDM 等）拦截，适用于非图片/大文件场景。
// 文件最终保存在系统 Downloads 目录下（filename 指定文件名）。
async function executeDownloadViaBlob(url, filename, msgId) {
    try {
        const response = await fetch(url, {
            credentials: 'include',
            cache: 'no-store'
        });
        if (!response.ok) {
            socket.send(JSON.stringify({
                id: msgId,
                status: 'error',
                error: `HTTP ${response.status}: ${response.statusText}`
            }));
            return;
        }
        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);

        chrome.downloads.download({
            url: blobUrl,
            filename: filename || 'download',
            conflictAction: 'uniquify',
            saveAs: false
        }, (downloadId) => {
            // blob URL 在 download 回调里才能安全释放
            setTimeout(() => URL.revokeObjectURL(blobUrl), 10000);
            if (chrome.runtime.lastError) {
                socket.send(JSON.stringify({
                    id: msgId,
                    status: 'error',
                    error: chrome.runtime.lastError.message
                }));
            } else {
                socket.send(JSON.stringify({
                    id: msgId,
                    status: 'success',
                    downloadId: downloadId,
                    mime: blob.type
                }));
            }
        });
    } catch (e) {
        socket.send(JSON.stringify({ id: msgId, status: 'error', error: e.toString() }));
    }
}

triggerConnect(false);
