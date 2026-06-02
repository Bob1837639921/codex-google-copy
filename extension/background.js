let socket = null;
let agentTabId = null;
let currentGroupId = null;

let retryCount = 0;
const MAX_RETRIES = 5;
let isExplicitlyPaused = false;
let connectTimeout = null;

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
    const tabs = await chrome.tabs.query({});
    for (let tab of tabs) {
      if (tab.url && (tab.url.startsWith('http://') || tab.url.startsWith('https://'))) {
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
        // 如果断掉或者找不到页面，强行新建页面兜底
        if (!agentTabId && data.action !== 'init') {
            await initAgentTab('AI 自动兜底新建', null);
        }

        if (data.action === 'init') {
            await initAgentTab(data.taskName || 'AI 正在执行', data.id);
        } else if (data.action === 'ping') {
            socket.send(JSON.stringify({ id: data.id, status: 'success', message: 'Extension connected' }));
        } else if (data.action === 'navigate') {
            await executeNavigate(data.url, data.id);
        } else if (data.action === 'evaluate') {
            await executeEvaluate(data.code, data.id);
        } else if (data.action === 'hover') {
            await executeHover(data.selector, data.id);
        } else if (data.action === 'click') {
            await executeClick(data.selector, data.id);
        } else if (data.action === 'type') {
            await executeType(data.selector, data.text, data.id);
        } else if (data.action === 'snapshot') {
            await executeSnapshot(data.id);
        } else if (data.action === 'download') {
            await executeDownload(data.url, data.filename, data.id);
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
            cursor.style.opacity = '0';
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
  }
  return true; // Keep message channel open for async response
});


async function initAgentTab(taskName, msgId) {
    if (agentTabId) {
        try {
            await chrome.tabs.get(agentTabId);
            if (currentGroupId) {
                await chrome.tabGroups.update(currentGroupId, { title: taskName });
            }
            await attachDebugger(agentTabId);
            if (msgId) {
                socket.send(JSON.stringify({ id: msgId, status: 'success', message: 'Tab already exists (and re-attached)' }));
            }
            return;
        } catch (e) {
            agentTabId = null;
            currentGroupId = null;
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
    chrome.debugger.sendCommand({ tabId: tabId }, method, params, (result) => {
      if (chrome.runtime.lastError) {
        reject(chrome.runtime.lastError.message);
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

async function ensureFakeCursor() {
    await ensureAgentTab();
    const code = `
        if (!document.getElementById('ai-fake-cursor')) {
            const cursor = document.createElement('div');
            cursor.id = 'ai-fake-cursor';
            cursor.style.position = 'fixed';
            cursor.style.zIndex = '2147483647';
            cursor.style.pointerEvents = 'none';
            cursor.style.width = '28px';
            cursor.style.height = '28px';
            cursor.style.background = 'url("data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'28\\' height=\\'28\\' viewBox=\\'0 0 24 24\\' fill=\\'%23FF3366\\' stroke=\\'white\\' stroke-width=\\'1.5\\' stroke-linecap=\\'round\\' stroke-linejoin=\\'round\\'%3E%3Cpolygon points=\\'3 3 10 21 14 14 21 10 3 3\\'%3E%3C/polygon%3E%3C/svg%3E") no-repeat';
            cursor.style.backgroundSize = 'contain';
            cursor.style.transition = 'top 0.6s ease-out, left 0.6s ease-out, opacity 0.4s ease-in-out, transform 0.15s ease-out';
            cursor.style.opacity = '0';
            cursor.style.top = '10px';
            cursor.style.left = '10px';
            cursor.style.filter = 'drop-shadow(2px 4px 6px rgba(0,0,0,0.3))';
            document.body.appendChild(cursor);
        }
    `;
    await sendCommand(agentTabId, 'Runtime.evaluate', { expression: code });
}

async function executeNavigate(url, msgId) {
  if (!agentTabId) await initAgentTab('AI 正在执行');
  
  await chrome.tabs.update(agentTabId, { url: url });
  
  setTimeout(async () => {
      await ensureFakeCursor();
      socket.send(JSON.stringify({ id: msgId, status: 'success' }));
  }, 3000);
}

async function executeEvaluate(code, msgId) {
  if (!agentTabId) await initAgentTab('AI 正在执行');

  const result = await sendCommand(agentTabId, 'Runtime.evaluate', {
    expression: code,
    returnByValue: true
  });
  
  socket.send(JSON.stringify({ id: msgId, status: 'success', result: result.result?.value }));
}

async function executeHover(selector, msgId) {
    await ensureFakeCursor();
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
                    // 1. 清理之前的隐藏定时器
                    if (window.__ai_cursor_hide_timeout) {
                        clearTimeout(window.__ai_cursor_hide_timeout);
                    }
                    
                    // 2. 显式设为可见并移动位置
                    cursor.style.opacity = '1';
                    cursor.style.left = (rect.left + rect.width / 2) + 'px';
                    cursor.style.top = (rect.top + rect.height / 2) + 'px';
                    
                    // 3. 注册新的延迟隐藏定时器，在 2.5 秒无操作后淡出消失
                    window.__ai_cursor_hide_timeout = setTimeout(() => {
                        const cur = document.getElementById('ai-fake-cursor');
                        if (cur) {
                            cur.style.opacity = '0';
                        }
                    }, 2500);
                }
            }, 300);
            return true;
        })();
    `;
    await sendCommand(agentTabId, 'Runtime.evaluate', { expression: codeMove });
    
    setTimeout(() => {
        if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'success' }));
    }, 1200); 
}

async function executeClick(selector, msgId) {
    await executeHover(selector, null); 
    const selectorLiteral = jsString(selector);
    
    setTimeout(async () => {
        const codeClick = `
            (() => {
                const el = document.querySelector(${selectorLiteral});
                if (el) { 
                    const cursor = document.getElementById('ai-fake-cursor');
                    if (cursor) {
                        cursor.style.transform = 'scale(0.8)';
                        setTimeout(() => cursor.style.transform = 'scale(1)', 150);
                    }
                    el.click(); 
                    return true; 
                }
                return false;
            })();
        `;
        await sendCommand(agentTabId, 'Runtime.evaluate', { expression: codeClick });
        if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'success' }));
    }, 1200); 
}

async function executeType(selector, text, msgId) {
    await executeHover(selector, null);
    const selectorLiteral = jsString(selector);
    
    setTimeout(async () => {
        // 关键1：先真正触发一次 DOM 级别的 click，确保框架内部的聚焦状态
        const codeClick = `
            (() => {
                const el = document.querySelector(${selectorLiteral});
                if (el) { 
                    el.focus();
                    el.click();
                    // 为了触发 React 的状态更新，直接修改其底层 value tracker
                    const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(proto, "value").set;
                    if (nativeInputValueSetter) {
                        nativeInputValueSetter.call(el, '');
                    } else {
                        el.value = '';
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    return true; 
                }
                return false;
            })();
        `;
        await sendCommand(agentTabId, 'Runtime.evaluate', { expression: codeClick });
        
        // 关键2：使用 CDP 的 insertText 强行插入文本（这等同于用户 Ctrl+V 粘贴或者输入法的直接上屏，最难被拦截）
        await sendCommand(agentTabId, 'Input.insertText', { text: text });
        
        // 关键3：为了保险，有些网站需要回车键触发
        await sendCommand(agentTabId, 'Input.dispatchKeyEvent', { type: 'keyDown', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });
        await sendCommand(agentTabId, 'Input.dispatchKeyEvent', { type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13, nativeVirtualKeyCode: 13 });

        if(msgId) socket.send(JSON.stringify({ id: msgId, status: 'success' }));
    }, 1200);
}

async function executeSnapshot(msgId) {
    await ensureAgentTab();
    const code = `
        (() => {
            const bodyText = document.body.innerText || '';
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
    const result = await sendCommand(agentTabId, 'Runtime.evaluate', { expression: code, returnByValue: true });
    const data = result.result?.value || { blockedByLogin: false, dom: [] };
    socket.send(JSON.stringify({ 
        id: msgId, 
        status: 'success', 
        blockedByLogin: data.blockedByLogin,
        dom: data.dom 
    }));
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

triggerConnect();
