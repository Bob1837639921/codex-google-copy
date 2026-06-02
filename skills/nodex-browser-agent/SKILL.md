---
name: nodex-browser-agent
description: Use the local NodeX Browser Agent Chrome automation bridge when a task needs Codex to control a locally installed Chrome extension through server_live.py and agent_core.py, including navigation, DOM snapshots, clicking, typing, hovering, or page JavaScript evaluation.
---

# NodeX Browser Agent

Use this skill when the user wants to control Chrome through this repository's local bridge.

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

## Workflow

1. Check whether `server_live.py` is already running before starting another server.
2. Connect through `agent_core.BrowserAgent`, which defaults to `ws://localhost:8765/client`.
3. Call `await agent.init("Task name")` before controlling a tab.
4. Before clicking or typing on shopping, login, payment, or verification pages, call `await agent.snapshot()`.
5. If `snapshot()["blocked_by_login"]` is true, stop automation and ask the user to handle login or verification manually.
6. Prefer high-level methods in `agent_core.py`: `navigate`, `snapshot`, `hover`, `click`, `type`, and `evaluate`.

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
