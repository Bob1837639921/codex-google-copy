---
name: nodex-browser-agent
description: Use the local NodeX Browser Agent bridge to control Chrome through WebSocket/CDP. Trigger this skill for browser automation, web navigation, form filling, scraping, downloads, DOM snapshots, visual screenshots, non-vision visual layout snapshots, semantic clicking/typing, or resilient multi-step action plans. Prefer reusable NodeX tools and JSON action plans over one-off scripts.
---

# NodeX Browser Agent

Use this skill when a task needs to control the user's local Chrome browser through this repository's bridge.

## Default Rule

Do not start by writing a new Python script. Prefer this order:

1. Use MCP tools named `nodex_*` if they are available.
2. Use `nodex_run_action_plan` or `python action_executor.py --plan plan.json` for multi-step tasks.
3. Use `agent_core.BrowserAgent` directly only when the reusable action plan vocabulary is not enough.
4. Write a new script only after identifying a reusable gap; then consider adding that capability back to `action_executor.py`.

The bridge routes Python clients through `ws://localhost:8765/client`. The Chrome extension connects to `ws://localhost:8765`.

## Chain Of Truth

These are facts, not suggestions:

1. **AI/MCP/SDK layer** creates commands or JSON action plans.
2. **Python client layer** connects to `ws://localhost:8765/client`.
3. **Bridge layer** in `server_live.py` forwards commands by id.
4. **Chrome extension layer** connects to `ws://localhost:8765` and executes CDP/debugger commands.
5. **Page layer** returns DOM data, screenshots, download responses, or action errors.

Do not blur these layers. The AI does not directly control Chrome; it asks the bridge to perform supported actions and must verify the returned evidence.

If MCP is available, call `nodex_capabilities` when unsure. It is the source of truth for supported tools, action-plan actions, locator fields, and route facts.

## Anti-Hallucination Contract

- Do not invent tool names, action names, selector syntax, or browser state.
- Do not claim a task is complete just because `click` or `type` returned success. Verify with `snapshot`, `screenshot`, `extract`, URL, or visible text.
- A `screenshot` captures pixels only. It does not interpret the image unless the calling AI or host reads that image.
- If the caller does not support vision, use `visual_snapshot` instead of pretending to inspect the screenshot.
- If the page state is unknown, run `snapshot` or `screenshot` before deciding the next step.
- If a selector fails, the next step is observe-and-repair, not guessing more clicks.
- If the user asks for an unsupported action, explain the gap and use the closest supported primitive only if it is safe.

## Connection Check

Before controlling Chrome:

```powershell
netstat -ano | findstr 8765
```

If port `8765` is not listening, start the bridge from the repository root:

```powershell
python -u server_live.py
```

On Windows, the packaged server can also be started:

```powershell
Start-Process -WindowStyle Hidden dist\server_live.exe
```

Make sure the Chrome extension in `extension/` is loaded in Chrome developer mode.

## Operating Loop

For every non-trivial browser task, run this loop:

1. **Observe**: take a DOM snapshot and inspect URL/page state; add `screenshot` for vision-capable callers or `visual_snapshot` for text-only callers when layout or overlays matter.
2. **Plan**: convert the user's request into a short JSON action plan.
3. **Act**: execute actions with semantic locators where possible.
4. **Verify**: extract evidence, inspect URL/text, or take another snapshot/screenshot.
5. **Repair**: if a step fails, retry with a different locator or wait condition.

Never blindly click or type after a failed step. Observe again first.

## Safety Rules

- Call `snapshot` before `click` or `type`.
- Use `screenshot` when DOM text is insufficient and a vision-capable model/tool will inspect the image.
- Use `visual_snapshot` when the model is text-only; it returns JSON layout evidence such as bounding boxes, visible text, roles, selectors, z-index, and likely overlays.
- If `blocked_by_login` is true, stop and ask the user to complete login, CAPTCHA, payment confirmation, or account verification manually.
- Do not try to bypass login walls, CAPTCHA, sliders, payment prompts, or account security prompts.
- Keep browser automation visible to the user when working on authenticated sites.
- Use `evaluate` only for trusted JavaScript that you wrote for this task.

## Action Plans

Use this shape:

```json
{
  "group_name": "Search and collect results",
  "stop_on_error": true,
  "steps": [
    { "action": "navigate", "url": "https://example.com", "wait_seconds": 3 },
    { "action": "wait_for", "placeholder": "Search", "timeout": 10 },
    { "action": "type", "placeholder": "Search", "value": "query text", "retries": 2 },
    { "action": "click", "text": "Search", "mode": "smart", "retries": 2 },
    { "action": "wait_for", "text": "Results", "timeout": 15 },
    { "action": "screenshot", "path": "debug/results.png" },
    { "action": "visual_snapshot", "key": "layout_after_search" },
    {
      "action": "extract",
      "key": "results",
      "js_extractor": "Array.from(document.querySelectorAll('a')).slice(0,10).map(a => ({text:a.innerText, href:a.href}))"
    }
  ]
}
```

Supported actions:

- `navigate`: `{ "url": "...", "wait_seconds": 3 }`
- `snapshot` or `observe`: saves visible DOM and login-wall state.
- `screenshot`: captures a PNG viewport or full-page image; use `path` to save locally and `full_page: true` when needed.
- `visual_snapshot`: text-only visual layout JSON for models without image input.
- `click`: semantic or CSS locator. Supported `"mode"` values:
  - `"smart"` (default): Simulates full event chain (pointerdown -> mousedown -> focus -> pointerup -> mouseup -> click) to bypass anti-bot heuristics and trigger React/Vue event listeners.
  - `"direct"`: Fast direct DOM `el.click()` in memory. Use ONLY for websites with no anti-bot or complex event handlers.
- `type`: semantic or CSS locator plus `value`. Automatically emulates human keyboard typing by typing character-by-character with randomized keystroke delays (50ms - 130ms jitter).
- `hover`: semantic or CSS locator.
- `wait`: fixed sleep with `seconds`.
- `wait_for`: wait for a locator, visible text, or a truthy JS expression.
- `scroll`: `{ "direction": "down", "amount": 800, "repeat": 3 }`
- `extract`: use `js_extractor` or a locator.
- `evaluate`: run trusted JavaScript.
- `checkpoint`: write current progress to JSON for handoff/resume.

Locator fields:

- `selector`: CSS selector.
- `text`: visible text contained in a button/link/element.
- `contains`: same as `text`; useful when wording is partial.
- `exact_text`: exact visible text.
- `placeholder`: input placeholder text.
- `label`: label text associated with an input.
- `aria_label`: accessible label.
- `name`: input name attribute.
- `role`: ARIA role.
- `tag`: optional tag filter.
- `index`: zero-based match index.

Prefer semantic locators (`placeholder`, `label`, `text`, `aria_label`) over brittle CSS when possible.

## Failure Policy

When an action fails:

1. Re-observe with `snapshot`.
2. Add a `wait_for` step if the page is still loading.
3. Try a different semantic locator before writing JavaScript.
4. Use `evaluate` only for page-specific extraction or a missing interaction primitive.
5. If the same blocker repeats, checkpoint and ask the user for help.

Common recoverable cases:

- element appears after delay: add `wait_for`.
- wording differs: switch from `exact_text` to `contains`.
- dynamic class names: avoid CSS classes and use text/placeholder/aria-label.
- infinite feed: use `scroll` plus `extract`.

Fatal cases:

- login wall, CAPTCHA, account risk page, payment confirmation, quota exhausted, or permission denied.

## Prompt Pattern For Smaller Models

When using a smaller model such as Gemini Flash, give it structured work instead of an open-ended instruction:

```text
Task: <what to accomplish>
Target site/page: <URL or current page>
Output needed: <exact data/report format>
Constraints: do not bypass login/CAPTCHA; stop on blocked_by_login.
Allowed actions: navigate, snapshot, screenshot, visual_snapshot, wait_for, click, type, scroll, extract, evaluate.
Locator preference: placeholder/label/text/aria_label before CSS.
Return only a JSON action plan with 3-8 steps, then verify with an extract or snapshot.
```

This reduces random script generation and makes failures easier to repair.

## Direct SDK Use

Use the SDK for custom logic that cannot be expressed as an action plan:

```python
import asyncio
from agent_core import BrowserAgent

async def main():
    agent = BrowserAgent("ws://localhost:8765/client")
    await agent.connect()
    await agent.init("NodeX task")
    await agent.navigate("https://www.google.com")
    snapshot = await agent.snapshot()
    if snapshot["blocked_by_login"]:
        await agent.close()
        return
    await agent.type("textarea[name='q']", "NodeX Browser Agent")
    await agent.close()

asyncio.run(main())
```

For downloads, prefer `smart_save(url, dest_path)` from `BrowserAgent`; it routes small images to direct local file writes and falls back to blob downloads for other files.
