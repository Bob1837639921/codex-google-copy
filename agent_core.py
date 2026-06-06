"""
NodeX Browser Agent Core SDK - WebSocket-based Premium Browser Controller
========================================================================
This SDK enables seamless in-memory control of the Chrome browser via the WebSocket bridge.
Optimized for AI Agents and automated LLM loops. No temporary scripts or file IPC needed.

Author: Antigravity Team
Date: 2026-06-01
License: MIT
"""

import asyncio
import base64
import json
import websockets
import uuid
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class BrowserAgent:
    """
    Main SDK Client for controlling the browser tab dynamically via a live WebSocket connection.
    Highly recommended for AI agents seeking precise DOM manipulation, visual micro-animations,
    and automatic login barrier detection.
    """
    def __init__(self, ws_url: str = "ws://localhost:8765/client"):
        self.ws_url = ws_url
        self.websocket = None
        self._loop = None

    async def connect(self):
        """
        Establishes an active WebSocket connection to the server_live.py bridge.
        """
        logging.info(f"Connecting to Browser Agent Bridge at {self.ws_url}...")
        try:
            self.websocket = await websockets.connect(self.ws_url, max_size=50 * 1024 * 1024)
            logging.info("Successfully connected to the Browser Agent Bridge!")
            return True
        except Exception as e:
            logging.error(f"Failed to connect to the Bridge: {e}. Make sure server_live.py is running.")
            raise e

    async def _send_command(self, action: str, **kwargs):
        """
        Internal method to pack, transmit, and block-await the response for a specific action.
        """
        if not self.websocket:
            raise RuntimeError("WebSocket is not connected. Call 'await agent.connect()' first.")
            
        cmd_id = str(uuid.uuid4())
        payload = {"id": cmd_id, "action": action}
        payload.update(kwargs)
        
        # Transmit command via WebSocket channel
        await self.websocket.send(json.dumps(payload))
        
        # Wait for the specific response with matching command ID
        async for message in self.websocket:
            try:
                data = json.loads(message)
                if data.get("id") == cmd_id:
                    if data.get("status") == "error":
                        raise RuntimeError(f"Browser action failed: {data.get('error')}")
                    return data
            except json.JSONDecodeError:
                pass # Ignore keepalive ping/status packets

    async def init(self, task_name: str = "AI Live Agent"):
        """
        初始化并接管 Chrome 标签页，在 Chrome 中将当前 Tab 归入醒目的 Cyan（青色）标签页组。
        【AI 行为引导】：
        - 启动任何浏览器交互前的【首要必须步骤】。请勿省略此步骤，否则后续指令将因未附着 Tab 而报错。
        - task_name 将直接展示在受控浏览器的标签页组名称上，用以向用户标明当前的任务名称。
        """
        logging.info(f"Initializing Browser Agent Group: '{task_name}'")
        return await self._send_command("init", taskName=task_name)

    async def navigate(self, url: str):
        """
        控制受控标签页导航到指定 URL，并自动挂载虚拟光标指纹遮罩。
        【AI 行为引导】：
        - 打开页面后，由于网络延迟或页面载入原因，强烈建议在 navigate 后加入适量的等待时间（如调用 wait 延迟，或使用 wait_for 判定加载状态）。
        - 遇到需要授权登录的敏感页面时，navigate 之后必须立即调用 snapshot() 进行“登录墙/验证码”的安全状态判定。
        """
        logging.info(f"Navigating browser to: {url}")
        return await self._send_command("navigate", url=url)

    async def hover(self, selector: str):
        """
        平滑移动虚拟光标到目标 CSS 选择器所匹配的元素正中心。
        【AI 行为引导】：
        - 在执行 click() 或 type() 之前，系统会自动在底层执行 hover 动画进行光标聚焦，通常无需手动显式调用此方法，除非需要专门模拟鼠标悬停以触发浮动菜单展示。
        """
        logging.info(f"Hovering fake cursor over: {selector}")
        return await self._send_command("hover", selector=selector)

    async def click(self, selector: str, mode: str = "smart"):
        """
        点击目标元素，自动伴随真实的虚拟光标物理移动路线与红圈点击波纹微动画效果。
        【AI 决策指南（防风控与多框架兼容的核心设计）】：
        - :param mode: 可传入 'smart'（默认） 或 'direct'。
        - 默认的 'smart' 模式会仿真并分发整条物理/DOM 点击事件链（pointerdown -> mousedown -> focus -> pointerup -> mouseup -> click）。
          小红书、淘宝、京东等具有高级反爬虫/风控体系的站点，或者使用了 React/Vue 复杂单页组件（如自定义下拉选择框、弹窗遮罩）的目标，【必须保持默认的 'smart' 状态】。
        - 仅当目标网站绝对没有风控阻断行为，或者需要极快触发简单静态按钮，并且智能事件链发生冲突时，方可使用 mode='direct' 回退到方案一（直接触发内存 el.click()）。
        """
        logging.info(f"Clicking element (mode={mode}): {selector}")
        return await self._send_command("click", selector=selector, mode=mode)

    async def type(self, selector: str, text: str, mode: str = "smart"):
        """
        向网页中的目标输入框（或 contentEditable 富文本容器）中输入指定文本。
        【AI 决策指南（拟人化输入安全防护）】：
        - :param mode: 可传入 'smart'（默认） 或 'direct'。
        - 默认的 'smart' 模式已在底层自动实现了【人类真实物理击键延迟模拟（50ms - 130ms 随机抖动）】。AI 在进行大文本或多段落输入时表现如同真人。小红书、淘宝等具有高级反爬虫/风控体系的站点，【必须保持默认的 'smart' 状态】。
        - 若目标网站绝对没有风控阻断行为（例如本地应用、ChatGPT等），或者需要极快触发大文本输入，可使用 mode='direct' 实现一次性填入，绕过逐字延时。
        - 请勿一次性发送海量文本或在极短时间内对同一个输入框频繁发起输入指令，防止被行为流控检测判定为爬虫。
        - 如果是富文本编辑器（如小红书创作者页面），输入前确保先选中该元素，输入完成后如页面未发生状态更新，应结合 snapshot() 或 wait_for() 检查输入状态。
        """
        logging.info(f"Typing into element (mode={mode}): {selector}")
        return await self._send_command("type", selector=selector, text=text, mode=mode)

    async def snapshot(self):
        """
        捕获并分析当前浏览器视口（Viewport）的关键交互元素布局，检测是否有安全验证阻碍。
        【AI 行为引导（不可逾越的安全红线）】：
        - 本方法返回的 dict 中，'blocked_by_login' 表明当前页面是否被“密码登录、短信登录、扫码、滑块验证、极客验证码或安全流控墙”阻断。
        - 如果 'blocked_by_login' 为 True，【AI 必须停止一切点击与输入尝试】，并立刻向人类用户汇报，等待用户在真机上手动完成安全验证/扫码后再继续，切勿尝试以脚本暴力破解滑块或验证码！
        """
        logging.info("Retrieving page DOM snapshot with login-wall detection...")
        response = await self._send_command("snapshot")
        return {
            "blocked_by_login": response.get("blockedByLogin", False),
            "dom": response.get("dom", [])
        }

    async def evaluate(self, js_code: str):
        """
        在受控页面的 Window 全局上下文中执行任意 JavaScript 代码，并阻塞等待返回其序列化结果。
        【AI 行为引导】：
        - 仅在标准 SDK 交互原语无法满足需求（如需要获取特定复杂 DOM 属性、自定义计算）时作为兜底使用。
        - 必须确保 js_code 是可以安全自执行且格式正确的 JavaScript 语句。
        """
        logging.info("Executing custom script evaluation on active page...")
        response = await self._send_command("evaluate", code=js_code)
        return response.get("result")

    async def verify_dom_state(self, expected_text_or_selector: str, timeout: int = 5) -> bool:
        """
        方案一（降级验证）：轮询检测 DOM 中是否出现指定的文本或选择器。
        【AI 决策指南】：
        - 当且仅当大模型视觉或快照验证不可用时，作为底层的保底验证机制调用。
        """
        logging.info(f"Verifying DOM state for '{expected_text_or_selector}' with timeout {timeout}s...")
        import json
        js_code = f"""
        (() => {{
            const target = {json.dumps(expected_text_or_selector)};
            if (document.querySelector(target)) return true;
            if (document.body && document.body.innerText.includes(target)) return true;
            return false;
        }})()
        """
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            result = await self.evaluate(js_code)
            if result is True:
                logging.info(f"DOM state verified successfully: '{expected_text_or_selector}'")
                return True
            await asyncio.sleep(0.5)
        logging.warning(f"DOM state verification failed: '{expected_text_or_selector}' not found.")
        return False

    async def screenshot(self, dest_path: str = None, full_page: bool = False) -> dict:
        """
        通过 Chrome 调试协议 (CDP) 捕获受控 Tab 的 PNG 视口截图。
        【AI 行为引导】：
        - 如果当前主模型/调用链路【具备多模态视觉能力】（能直接读取图片），可通过调用此方法将图片写入 dest_path 供视觉模型分析来核对页面状态。
        - 若主模型为纯文本模型，请改用 visual_snapshot()。
        """
        logging.info("Capturing browser screenshot...")
        response = await self._send_command("screenshot", fullPage=full_page)
        b64_data = response.get("base64", "")
        result = {
            "status": response.get("status", "success"),
            "mime": response.get("mime", "image/png"),
            "base64": b64_data,
            "full_page": response.get("fullPage", full_page),
        }
        if dest_path:
            parent = os.path.dirname(dest_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            raw_bytes = base64.b64decode(b64_data)
            with open(dest_path, "wb") as f:
                f.write(raw_bytes)
            result.update({"path": dest_path, "size": len(raw_bytes)})
        return result

    async def visual_snapshot(self, limit: int = 80) -> dict:
        """
        专为【纯文本 AI 模型】设计的排版与层级结构快照，返回视口内可见元素的坐标、文本、role 和 selector。
        【AI 行为引导】：
        - 如果你的主模型接口没有 vision 视觉多模态能力，无法直接读懂 screenshot() 的图片，你必须调用此方法来“间接观察”页面元素排版、坐标以及寻找交互用选择器。
        - 限制参数 limit 可规避大规模 DOM 导致上下文爆满。
        """
        limit = max(1, min(int(limit), 200))
        js_code = f"""
(() => {{
  const limit = {limit};
  const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
  const escapeCss = (value) => {{
    if (window.CSS && CSS.escape) return CSS.escape(String(value));
    return String(value).replace(/[^a-zA-Z0-9_-]/g, (ch) => "\\\\" + ch);
  }};
  const selectorFor = (el) => {{
    if (el.id) return "#" + escapeCss(el.id);
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body) {{
      let part = node.tagName.toLowerCase();
      if (node.getAttribute("name")) part += `[name="${{String(node.getAttribute("name")).replace(/"/g, "\\\\\"")}}"]`;
      const parent = node.parentElement;
      if (parent) {{
        const siblings = Array.from(parent.children).filter((child) => child.tagName === node.tagName);
        if (siblings.length > 1) part += `:nth-of-type(${{siblings.indexOf(node) + 1}})`;
      }}
      parts.unshift(part);
      node = parent;
    }}
    return parts.length ? parts.join(" > ") : null;
  }};
  const textOf = (el) => clean([
    el.innerText,
    el.value,
    el.placeholder,
    el.getAttribute("aria-label"),
    el.getAttribute("title"),
    el.name
  ].filter(Boolean).join(" "));
  const visible = (el) => {{
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden" && Number(style.opacity || 1) > 0;
  }};
  const viewport = {{
    width: window.innerWidth,
    height: window.innerHeight,
    scrollX: window.scrollX,
    scrollY: window.scrollY,
    url: window.location.href,
    title: document.title
  }};
  const query = [
    "a", "button", "input", "textarea", "select", "summary",
    "[role]", "[contenteditable='true']", "[tabindex]",
    "h1", "h2", "h3", "h4", "label", "img", "video", "canvas"
  ].join(",");
  const items = Array.from(document.querySelectorAll(query))
    .filter(visible)
    .map((el) => {{
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      const tag = el.tagName.toLowerCase();
      return {{
        tag,
        role: el.getAttribute("role") || null,
        type: el.getAttribute("type") || null,
        selector: selectorFor(el),
        text: textOf(el).slice(0, 220),
        href: el.href || null,
        src: el.currentSrc || el.src || null,
        box: {{
          x: Math.round(rect.left),
          y: Math.round(rect.top),
          width: Math.round(rect.width),
          height: Math.round(rect.height)
        }},
        center: {{
          x: Math.round(rect.left + rect.width / 2),
          y: Math.round(rect.top + rect.height / 2)
        }},
        zIndex: style.zIndex === "auto" ? null : style.zIndex,
        position: style.position,
        viewportVisible: rect.bottom >= 0 && rect.right >= 0 && rect.top <= window.innerHeight && rect.left <= window.innerWidth
      }};
    }})
    .filter((item) => item.viewportVisible)
    .sort((a, b) => {{
      const za = Number.parseInt(a.zIndex || "0", 10) || 0;
      const zb = Number.parseInt(b.zIndex || "0", 10) || 0;
      if (zb !== za) return zb - za;
      return (a.box.y - b.box.y) || (a.box.x - b.box.x);
    }})
    .slice(0, limit);
  const overlays = items.filter((item) => {{
    const area = item.box.width * item.box.height;
    const viewportArea = Math.max(1, viewport.width * viewport.height);
    return area / viewportArea > 0.2 || item.position === "fixed" || item.position === "sticky";
  }}).slice(0, 12);
  return {{ viewport, items, overlays }};
}})()
"""
        return await self.evaluate(js_code)

    async def download(self, url: str, filename: str):
        """
        Triggers a download of the given URL inside Chrome, saving it under the specified filename.
        Uses chrome.downloads API in the background.js extension.
        :param url: Complete HTTP/HTTPS URL of the target file.
        :param filename: Desired relative path/name in the downloads directory (e.g. 'cover.png').
        """
        logging.info(f"Triggering extension download from {url} to {filename}...")
        return await self._send_command("download", url=url, filename=filename)

    async def search_downloads(self, query: dict = None):
        """
        Queries the history of downloads using the chrome.downloads.search API.
        """
        logging.info(f"Searching downloads with query: {query}...")
        return await self._send_command("searchDownloads", query=query or {})

    async def fetch_as_file(self, url: str, dest_path: str) -> dict:
        """
        【仅适用于图片文件，< 30MB】
        扩展后台带 Cookie fetch URL → base64 → Python 直接写入 dest_path。
        完全绕过 chrome.downloads，FDM 等下载管理器无感知。
        不需要中转 Downloads 文件夹，支持写入任意本地路径。
        """
        import base64, os
        logging.info(f"fetch_as_file: {url[:60]}... → {dest_path}")
        response = await self._send_command("fetchAsBase64", url=url)
        if not response or response.get("status") != "success":
            error = response.get("error", "Unknown error") if response else "No response"
            reason = response.get("reason", "") if response else ""
            logging.error(f"fetchAsBase64 failed [{reason}]: {error}")
            return {"status": "error", "error": error, "reason": reason}
        b64_data = response.get("base64", "")
        raw_bytes = base64.b64decode(b64_data)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)
        size = len(raw_bytes)
        logging.info(f"Saved {size:,} bytes → {dest_path}")
        return {"status": "success", "path": dest_path, "size": size, "mime": response.get("mime", "")}

    async def download_via_blob(self, url: str, filename: str) -> dict:
        """
        【适用于非图片文件或大文件】
        扩展 Service Worker 带 Cookie fetch URL → 生成 blob: URL → chrome.downloads 下载。
        blob: URL 不会被 FDM 等第三方下载管理器拦截，后台安全，无需窗口唤醒。
        文件保存在系统 Downloads 目录，filename 指定文件名。

        :param url:      要下载的 HTTP/HTTPS URL。
        :param filename: 保存的文件名（如 'report.pdf'），落在系统 Downloads 文件夹下。
        :return:         dict: {status, downloadId, mime}
        """
        logging.info(f"download_via_blob: {url[:60]}... → Downloads/{filename}")
        return await self._send_command("downloadViaBlob", url=url, filename=filename)

    async def smart_save(self, url: str, dest_path: str) -> dict:
        """
        智能路由下载工具，根据文件类型自动选择最优的无感知后台下载机制。
        【AI 决策指南】：
        - 凡是遇到需要从已登录页面下载图片、导出 PDF、截图归档或获取其他文件资源的场景，【强烈建议优先调用此方法】。
        - 它会自动路由：图片类直接 fetch 绕过拦截写入 dest_path 任意本地路径；非图片或大文件走 Blob 下载回退至系统 Downloads 目录。
        """
        import os
        # 先尝试 fetch_as_file（图片路径）
        logging.info(f"smart_save: 尝试 fetch_as_file → {dest_path}")
        result = await self.fetch_as_file(url, dest_path)
        if result.get("status") == "success":
            return result

        reason = result.get("reason", "")
        # 如果是不支持的文件类型或文件过大，自动回退到 download_via_blob
        if reason in ("unsupported_mime", "file_too_large"):
            filename = os.path.basename(dest_path)
            logging.info(f"smart_save: 回退到 download_via_blob，filename={filename}（原因：{reason}）")
            return await self.download_via_blob(url, filename)

    async def smart_click(self, selector: str):
        """
        向目标元素直接注入底层的 Pointer/Mouse/Focus 完整交互事件链。
        【AI 决策指南】：
        - 现有的默认 click() 方法在底层已内置了相同的 smart 智能事件分发机制，并伴有光标运动动画，因此请【优先直接使用标准的 click()】。
        - 仅当标准的 click() 因层级冲突或定位失败，且你想尝试在当前 tab 页面直接注入 JS 分发事件时，方可调用此方法。
        """
        logging.info(f"Smart clicking element: {selector}")
        import json
        js_code = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return "Element not found";
            
            const opts = {{ bubbles: true, cancelable: true, view: window }};
            el.dispatchEvent(new PointerEvent('pointerdown', opts));
            el.dispatchEvent(new MouseEvent('mousedown', opts));
            if (typeof el.focus === 'function') el.focus();
            el.dispatchEvent(new PointerEvent('pointerup', opts));
            el.dispatchEvent(new MouseEvent('mouseup', opts));
            el.click();
            return "Events dispatched";
        }})()
        """
        return await self.evaluate(js_code)

    async def smart_fill_select(self, label_text: str, search_text: str, option_text: str):
        """
        全自动表单项匹配与下拉选择工具，专为 Ant Design / Element Plus 等复杂自定义 Select 下拉框设计。
        【AI 决策指南】：
        - 如果网页表单中的下拉选择框（Select）并非标准 HTML `<select>` 标签，而是由复杂的复合 `div/span` 模拟的自定义组件，使用常规的 click() 和 type() 会极其容易失败或导致下拉列表关闭。
        - 此时，必须调用此方法。只需提供关联的 Label 文本、选填的过滤搜索词以及期望选择的 Option 文本，它会自动在底层完成点击展开、搜索匹配并选中的复合动作。
        """
        logging.info(f"Smart filling select for label '{label_text}' with option '{option_text}'")
        import json
        js_code = f"""
        (async () => {{
            const sleep = ms => new Promise(r => setTimeout(r, ms));
            
            const findInputByLabel = (labelVal) => {{
                const items = Array.from(document.querySelectorAll('.ant-form-item, [class*="form-item"]'));
                const item = items.find(el => {{
                    const label = el.querySelector('.ant-form-item-label, label');
                    return label && label.innerText.includes(labelVal);
                }});
                if (!item) return null;
                return item.querySelector('input');
            }};
            
            const input = findInputByLabel({json.dumps(label_text)});
            if (!input) return {{ "status": "error", "message": "Label not found" }};
            
            const wrapper = input.closest('.ant-select')?.querySelector('.ant-select-selector') || input;
            if (!wrapper) return {{ "status": "error", "message": "Select wrapper not found" }};
            
            // 1. Open dropdown
            wrapper.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}));
            wrapper.click();
            await sleep(800);
            
            // 2. Type search text if needed
            const searchVal = {json.dumps(search_text)};
            if (searchVal) {{
                input.focus();
                input.value = '';
                document.execCommand('insertText', false, searchVal);
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                await sleep(1500);
            }}
            
            // 3. Find option matching optionText in active dropdown
            const optVal = {json.dumps(option_text)};
            const options = Array.from(document.querySelectorAll('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option'));
            const targetOpt = options.find(opt => opt.innerText.includes(optVal));
            if (targetOpt) {{
                targetOpt.click();
                await sleep(800);
                return {{ "status": "success", "message": "Option selected" }};
            }} else {{
                // Close dropdown if option not found
                document.body.dispatchEvent(new MouseEvent('mousedown', {{ bubbles: true }}));
                document.body.click();
                return {{ "status": "error", "message": "Option not found in visible dropdown" }};
            }}
        }})()
        """
        return await self.evaluate(js_code)

    @staticmethod
    def sanitize_text(text: str, strip_emojis: bool = True) -> str:
        """
        Sanitizes text by removing emojis and non-BMP symbols to comply with input constraints.
        """
        if not text:
            return ""
        if strip_emojis:
            import re
            # Match emoji patterns and non-BMP characters
            emoji_pattern = re.compile(
                '['
                '\U00010000-\U0010ffff'  # non-BMP characters / emojis
                '\u2600-\u27BF'          # Misc Symbols & Dingbats
                '\u2300-\u23FF'          # Misc Technical Symbols
                '\u2b50'                 # Medium Black Star
                ']', flags=re.UNICODE
            )
            text = emoji_pattern.sub('', text)
        return text

    async def handle_modal(self, contains_text: str, click_selector: str = None):
        """
        Detects if a modal containing specific text is present, and optionally clicks a button inside it.
        """
        logging.info(f"Checking for modal containing text: '{contains_text}'")
        import json
        js_code = f"""
        (() => {{
            const modals = Array.from(document.querySelectorAll('.ant-modal-content, .ant-modal, [class*="modal"]'));
            const activeModal = modals.find(m => m.innerText.includes({json.dumps(contains_text)}));
            if (!activeModal) return {{ "status": "not_found" }};
            
            if ({json.dumps(click_selector)}) {{
                const target = activeModal.querySelector({json.dumps(click_selector)});
                if (target) {{
                    target.click();
                    return {{ "status": "success", "action": "clicked_target" }};
                }}
            }}
            
            // Fallback: try finding button inside the modal
            const button = activeModal.querySelector('button');
            if (button) {{
                button.click();
                return {{ "status": "success", "action": "clicked_fallback_button" }};
            }}
            
            return {{ "status": "found", "action": "none" }};
        }})()
        """
        return await self.evaluate(js_code)

    async def close(self):
        """
        Closes the WebSocket connection gracefully.
        """
        if self.websocket:
            await self.websocket.close()
            logging.info("Browser Agent connection closed.")
