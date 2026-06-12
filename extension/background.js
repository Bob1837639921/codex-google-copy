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

function jsString(value) {
  return JSON.stringify(String(value));
}

// 每20秒发一次心跳，防止 Chrome 休眠
let keepAliveInterval = setInterval(() => {
    if (socket && socket.readyState === 1 /* WebSocket.OPEN */) {
        socket.send(JSON.stringify({ type: 'ping' }));
    }
}, 20000);

async function hasHttpOrHttpsTab() {
  try {
    const tabs = await chrome.tabs.query({ active: true });
    for (let tab of tabs) {
      if (tab.url && (tab.url.includes('chatgpt.com') || tab.url.includes('localhost') || tab.url.includes('127.0.0.1'))) {
        return true;
      }
    }
  } catch (e) {
    console.log('Error querying tabs:', e);
  }
  return false;
}

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
  
  const hasTab = await hasHttpOrHttpsTab();
  if (!hasTab && !force) {
    console.log('[Connection] No active HTTP/HTTPS tabs. Staying silent to avoid error logs.');
    return;
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

        // 如果断掉或者找不到页面，强行新建页面兜底（仅针对需要 tabId 的页面操控指令）
        const needsTabId = ['navigate', 'evaluate', 'hover', 'click', 'type', 'snapshot', 'screenshot'];
        if (!tabId && needsTabId.includes(data.action)) {
            await initAgentTab('AI 自动兜底新建', null, sid);
            tabId = sessions[sid].tabId;
        }

        if (tabId && data.action !== 'init' && data.action !== 'listTabs' && data.action !== 'getErrorLog' && data.action !== 'testFind') {
            await chrome.tabs.update(tabId, { active: true }).catch(() => {});
        }

        if (data.action === 'init') {
            await initAgentTab(data.taskName || 'AI 正在执行', data.id, data.sessionId);
        } else if (data.action === 'ping') {
            socket.send(JSON.stringify({ id: data.id, status: 'success', message: 'Extension connected' }));
        } else if (data.action === 'navigate') {
            await executeNavigate(tabId, data.url, data.id);
        } else if (data.action === 'evaluate') {
            await executeEvaluate(tabId, data.code, data.id);
        } else if (data.action === 'hover') {
            await executeHover(tabId, data.selector, data.id);
        } else if (data.action === 'click') {
            await executeClick(tabId, data.selector, data.mode, data.id);
        } else if (data.action === 'type') {
            await executeType(tabId, data.selector, data.text, data.mode, data.id);
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
        } else if (data.action === 'reloadExtension') {
            socket.send(JSON.stringify({ id: data.id, status: 'success', message: 'Reloading extension...' }));
            setTimeout(() => {
                chrome.runtime.reload();
            }, 150);
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
    triggerConnect();
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
      triggerConnect();
    }
  } catch (e) {}
});

// 监听标签页手动关闭事件，及时同步状态
chrome.tabs.onRemoved.addListener((tabId) => {
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

    // 智能特性：如果浏览器中任何标签页是 chatgpt.com，直接接管它，不新建 about:blank
    try {
        const tabs = await chrome.tabs.query({});
        const chatgptTab = tabs.find(t => t.url && t.url.includes('chatgpt.com'));
        if (chatgptTab) {
            agentTabId = chatgptTab.id;
            
            // 调试器附着是必选核心步骤，首先执行
            await attachDebugger(agentTabId);
            await chrome.tabs.update(agentTabId, { active: true });
            
            // 标签页分组为可选外观属性，即使权限或分组限制导致报错也不影响核心功能
            try {
                currentGroupId = await chrome.tabs.group({ tabIds: [agentTabId] });
                await chrome.tabGroups.update(currentGroupId, { 
                    title: taskName, 
                    color: 'cyan'
                });
            } catch (groupErr) {
                console.warn('Failed to group tab:', groupErr);
                lastErrorLog.push('Grouping failed (non-fatal): ' + groupErr.toString());
            }
            
            sessions[sid] = {
                tabId: agentTabId,
                groupId: currentGroupId
            };
            if (msgId) {
                socket.send(JSON.stringify({ id: msgId, status: 'success', message: 'Attached to ChatGPT tab' }));
            }
            return;
        }
    } catch (e) {
        console.error('Error auto-attaching to ChatGPT tab:', e);
        lastErrorLog.push('auto-attach error: ' + e.toString() + ' stack: ' + e.stack);
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
        groupId: currentGroupId
    };
    
    if (msgId) {
        socket.send(JSON.stringify({ id: msgId, status: 'success', message: 'Tab created and grouped' }));
    }
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

async function sendCommand(tabId, method, params = {}) {
  return new Promise((resolve, reject) => {
    chrome.debugger.sendCommand({ tabId: tabId }, method, params, async (result) => {
      if (chrome.runtime.lastError) {
        const errMsg = chrome.runtime.lastError.message;
        if (errMsg && (errMsg.includes("Debugger is not attached") || errMsg.includes("not attached to the tab"))) {
          console.warn(`[Debugger] Detached detected. Attempting to auto re-attach to tab ${tabId}...`);
          try {
            await attachDebugger(tabId);
            chrome.debugger.sendCommand({ tabId: tabId }, method, params, (retryResult) => {
              if (chrome.runtime.lastError) {
                reject(chrome.runtime.lastError.message);
              } else {
                resolve(retryResult);
              }
            });
          } catch (attachErr) {
            reject(`Failed to re-attach debugger: ${attachErr}. Original error: ${errMsg}`);
          }
        } else {
          reject(errMsg);
        }
      } else {
        resolve(result);
      }
    });
  });
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

async function executeNavigate(tabId, url, msgId) {
  await chrome.tabs.update(tabId, { url: url, active: true });
  
  setTimeout(async () => {
      try {
          await ensureFakeCursor(tabId);
          socket.send(JSON.stringify({ id: msgId, status: 'success' }));
      } catch (e) {
          console.error("Error in executeNavigate timeout:", e);
          socket.send(JSON.stringify({ id: msgId, status: 'success', warning: e.toString() }));
      }
  }, 3000);
}

async function executeEvaluate(tabId, code, msgId) {
  await touchFakeCursor(tabId);
  const result = await sendCommand(tabId, 'Runtime.evaluate', {
    expression: code,
    returnByValue: true,
    awaitPromise: true
  });
  
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
                (() => {
                    const el = document.querySelector(${selectorLiteral});
                    if (el) { 
                        const cursor = document.getElementById('ai-fake-cursor');
                        if (cursor && window.__ai_cursor_pulse) {
                            window.__ai_cursor_pulse();
                        }
                        const runMode = ${modeLiteral};
                        setTimeout(() => {
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
                        }, 50);
                        return true; 
                    }
                    return false;
                })();
            `;
            const clickResult = await sendCommand(tabId, 'Runtime.evaluate', { expression: codeClick, returnByValue: true });
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

async function executeType(tabId, selector, text, mode, msgId) {
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
            
            await sendCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
            await sendCommand(tabId, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
 
            if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'success' }));
        } catch (e) {
            console.error("Error in executeType timeout:", e);
            if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'error', error: e.toString() }));
        }
    }, 1200);
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
                dom: Array.from(new Set(items)).slice(0, 80)
            };
        })();
    `;
    const result = await sendCommand(tabId, 'Runtime.evaluate', { expression: code, returnByValue: true });
    const data = result.result?.value || { blockedByLogin: false, dom: [] };
    socket.send(JSON.stringify({ 
        id: msgId, 
        status: 'success', 
        blockedByLogin: data.blockedByLogin,
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
        if (mime && !ALLOWED_MIME_PREFIXES.some(prefix => mime.startsWith(prefix))) {
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
