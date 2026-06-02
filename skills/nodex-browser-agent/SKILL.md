---
name: nodex-browser-agent
description: Use the local NodeX Browser Agent Chrome automation bridge when a task needs Codex to control a locally installed Chrome extension through server_live.py and agent_core.py, including navigation, DOM snapshots, clicking, typing, hovering, page JavaScript evaluation, and downloading files via the chrome.downloads API.
---

# NodeX Browser Agent

Use this skill when the user wants to control Chrome through this repository's local bridge.

When the plugin's MCP server is installed, prefer its `nodex_*` tools over writing one-off scripts.

## Requirements

- The Chrome extension in `extension/` must be loaded as an unpacked extension.
- The bridge server must be running from the repository root:

```bash
python server_live.py
```

- Python dependencies must be installed:

```bash
pip install -r requirements.txt
```

## SDK Methods

All methods are available on `agent_core.BrowserAgent`:

| Method | Description |
|--------|-------------|
| `connect()` | Open WebSocket connection to the bridge |
| `init(task_name)` | Attach to / create controlled Chrome tab group |
| `navigate(url)` | Navigate the controlled tab to a URL |
| `snapshot()` | Get DOM snapshot and login-wall detection result |
| `hover(selector)` | Move cursor to a CSS selector |
| `click(selector)` | Click a CSS selector |
| `type(selector, text)` | Type text into an input element |
| `evaluate(js_code)` | Execute JavaScript and return the result |
| `download(url, filename)` | Download a file via `chrome.downloads.download` API |
| `search_downloads(query)` | Query Chrome download history via `chrome.downloads.search` |
| `close()` | Close the WebSocket connection gracefully |

## MCP Tools

The plugin exposes these tools through `scripts/nodex_mcp_server.py`:

- `nodex_status`: check local bridge and extension connectivity.
- `nodex_init`: create or attach the controlled Chrome tab group.
- `nodex_navigate`: navigate the controlled tab to a URL.
- `nodex_snapshot`: inspect visible DOM elements and login-wall state.
- `nodex_hover`: move the visible cursor to a selector.
- `nodex_click`: click a selector after the safety snapshot check.
- `nodex_type`: type text after the safety snapshot check.
- `nodex_evaluate`: run trusted JavaScript in the controlled tab.
- `nodex_download`: trigger a background-safe download from a URL.
- `nodex_search_downloads`: query recent download history.
- `nodex_run_action_plan`: execute a sequential JSON action plan.

## Workflow

1. Check whether `server_live.py` is already running before starting another server.
2. Connect through `agent_core.BrowserAgent`, which defaults to `ws://localhost:8765/client`.
3. Call `await agent.init("Task name")` before controlling a tab.
4. Before clicking or typing on shopping, login, payment, or verification pages, call `await agent.snapshot()`.
5. If `snapshot()["blocked_by_login"]` is true, stop automation and ask the user to handle login or verification manually.
6. To download a file: use `await agent.download(url, filename)` — this is background-safe and does NOT require the page to be the active tab.

## Chrome Downloads API Pattern

For image pipeline workflows (e.g., saving ChatGPT DALL-E images automatically):

1. Record all pre-existing DALL-E image `src` URLs via `evaluate()`.
2. Send a generation prompt via `type()` + `evaluate()` (click send button).
3. Poll with `evaluate()` every 5 seconds until a NEW image URL appears.
4. Call `await agent.download(new_url, "cover.png")` to trigger the browser download.
5. Wait 5 seconds for disk write, then `os.rename()` the file to your archive folder.
6. Update your local database (e.g., `info.json`) with the new image entry.

## Safety Notes

- The extension has broad Chrome debugger access and should only connect to the local bridge.
- Do not execute untrusted action plans or arbitrary JavaScript.
- Do not try to bypass CAPTCHA, slider checks, login walls, payment confirmation, or account-security prompts.
- Keep automation visible and user-supervised when interacting with authenticated websites.

## Minimal Example

```python
import asyncio
from agent_core import BrowserAgent

async def main():
    agent = BrowserAgent()
    await agent.connect()
    await agent.init("Codex Browser Task")
    await agent.navigate("https://www.google.com")
    snapshot = await agent.snapshot()
    if snapshot["blocked_by_login"]:
        return
    await agent.close()

asyncio.run(main())
```

## Image Pipeline Example

```python
import asyncio, os, time
from agent_core import BrowserAgent

CHATGPT_URL = "https://chatgpt.com/c/<your-session-id>"
DOWNLOADS   = "C:/Users/<user>/Downloads"

async def main():
    agent = BrowserAgent()
    await agent.connect()
    await agent.init("Image Pipeline")
    await agent.navigate(CHATGPT_URL)
    await asyncio.sleep(6.0)

    # Record pre-existing DALL-E image URLs
    scan_js = """
    (() => {
        const imgs = Array.from(document.querySelectorAll('img'));
        return imgs.map(i => i.src).filter(s =>
            s && (s.includes('oaiusercontent.com') || s.includes('estuary/content'))
            && !s.includes('profile')
        );
    })()
    """
    pre_srcs = set(await agent.evaluate(scan_js) or [])

    # Send a generation prompt
    await agent.type("#prompt-textarea", "Draw a portrait, masterpiece, 8k.")
    await asyncio.sleep(1.5)
    await agent.evaluate("""
        (() => {
            const btn = document.querySelector('button[data-testid="send-button"]');
            if (btn) btn.click();
        })()
    """)

    # Poll for a new DALL-E image
    new_url = None
    for _ in range(45):
        await asyncio.sleep(5.0)
        current = await agent.evaluate(scan_js) or []
        new = [s for s in current if s not in pre_srcs]
        if new:
            new_url = new[-1]
            break

    if not new_url:
        print("Image not detected.")
        await agent.close()
        return

    # Download via chrome.downloads API (background-safe)
    result = await agent.download(new_url, "cover.png")
    print("Download result:", result)   # {'status': 'success', 'downloadId': 95}

    # Archive the file
    await asyncio.sleep(5.0)
    src = os.path.join(DOWNLOADS, "cover.png")
    dst = "C:/Ai/character/MyChar/01-main/cover.png"
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(src):
        os.rename(src, dst)
        print("Archived to:", dst)

    await agent.close()

asyncio.run(main())
```
