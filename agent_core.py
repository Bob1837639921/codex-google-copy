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
import json
import websockets
import uuid
import logging

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
        Initializes/hooks onto a Chrome tab and highlights it with a colored Cyan tab group.
        :param task_name: The visual label displaying in the active Chrome Tab Group.
        """
        logging.info(f"Initializing Browser Agent Group: '{task_name}'")
        return await self._send_command("init", taskName=task_name)

    async def navigate(self, url: str):
        """
        Navigates the browser to the specified URL. Automatically injects standard visual pointers.
        :param url: Complete HTTP/HTTPS URL.
        """
        logging.info(f"Navigating browser to: {url}")
        return await self._send_command("navigate", url=url)

    async def hover(self, selector: str):
        """
        Positions the visual cursor directly on the center of the elements matching the CSS selector.
        :param selector: Standard CSS selector (e.g. '#search-btn', 'button.submit').
        """
        logging.info(f"Hovering fake cursor over: {selector}")
        return await self._send_command("hover", selector=selector)

    async def click(self, selector: str):
        """
        Triggers a smooth hover animation, highlights a click pulse, and dispatches a DOM click event.
        :param selector: Standard CSS selector targeting the interactive element.
        """
        logging.info(f"Clicking element: {selector}")
        return await self._send_command("click", selector=selector)

    async def type(self, selector: str, text: str):
        """
        Types the given text inside the target input element. Ensures compatibility with React/Vue 
        change listeners via CDP typing emulation, followed by an automated Enter key trigger.
        :param selector: CSS selector of the input field.
        :param text: Text string to insert.
        """
        logging.info(f"Typing '{text}' into element: {selector}")
        return await self._send_command("type", selector=selector, text=text)

    async def snapshot(self):
        """
        Scrapes key interactive elements (links, buttons, inputs) in the viewport and returns 
        the page layout. Highly optimized to identify modal login barriers.
        
        :return: A dict with:
                 - "blocked_by_login": bool (True if a login dialog/wall is active)
                 - "dom": list (String array describing accessible elements and selectors)
        """
        logging.info("Retrieving page DOM snapshot with login-wall detection...")
        response = await self._send_command("snapshot")
        return {
            "blocked_by_login": response.get("blockedByLogin", False),
            "dom": response.get("dom", [])
        }

    async def evaluate(self, js_code: str):
        """
        Executes arbitrary Javascript code on the active page and returns its serialized result.
        :param js_code: String containing self-invoking or standard JavaScript statements.
        """
        logging.info("Executing custom script evaluation on active page...")
        response = await self._send_command("evaluate", code=js_code)
        return response.get("result")

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
        智能路由下载方法，自动选择最优下载方式：

        - 图片文件（image/*，< 30MB）→ fetch_as_file()
            · 直接写入 dest_path（任意本地路径）
            · 完全绕过 chrome.downloads，FDM 无感知

        - 其他文件 / 大文件 → download_via_blob()
            · 扩展 fetch → blob: URL → chrome.downloads
            · FDM 不拦截 blob: URL，文件保存到系统 Downloads 目录
            · 注意：dest_path 此时仅用于提取文件名，最终落在 Downloads 文件夹

        :param url:       完整 HTTP/HTTPS URL。
        :param dest_path: 目标路径（图片时直接写入；非图片时仅取文件名）。
        :return:          下载结果 dict。
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

        # 其他错误直接返回
        return result


    async def close(self):
        """
        Closes the WebSocket connection gracefully.
        """
        if self.websocket:
            await self.websocket.close()
            logging.info("Browser Agent connection closed.")
