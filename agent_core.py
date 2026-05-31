"""
Codex Browser Agent Core SDK - WebSocket-based Premium Browser Controller
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
    def __init__(self, ws_url: str = "ws://localhost:8765"):
        self.ws_url = ws_url
        self.websocket = None
        self._loop = None

    async def connect(self):
        """
        Establishes an active WebSocket connection to the server_live.py bridge.
        """
        logging.info(f"Connecting to Browser Agent Bridge at {self.ws_url}...")
        try:
            self.websocket = await websockets.connect(self.ws_url)
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

    async def close(self):
        """
        Closes the WebSocket connection gracefully.
        """
        if self.websocket:
            await self.websocket.close()
            logging.info("Browser Agent connection closed.")
