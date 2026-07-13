#!/usr/bin/env python3
"""MCP stdio server for the NodeX Chrome automation bridge."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent_core import BrowserAgent  # noqa: E402
from action_executor import UniversalActionExecutor  # noqa: E402
from auto_operator import AutoOperator, AutoOperatorConfig  # noqa: E402


PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT = 45


def configure_stdio_utf8(*streams: Any) -> None:
    for stream in streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        with contextlib.suppress(AttributeError, OSError, ValueError):
            reconfigure(encoding="utf-8", errors="strict")


configure_stdio_utf8(sys.stdin, sys.stdout, sys.stderr)


def text_content(value: Any) -> list[dict[str, str]]:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    return [{"type": "text", "text": text}]


def ok(value: Any) -> dict[str, Any]:
    return {"content": text_content(value)}


async def with_agent(
    handler: Callable[[BrowserAgent], Awaitable[Any]],
    *,
    timeout: int = DEFAULT_TIMEOUT,
    init_task_name: str | None = None,
) -> Any:
    agent = BrowserAgent()
    try:
        await asyncio.wait_for(agent.connect(), timeout=10)
        if init_task_name:
            await asyncio.wait_for(agent.init(init_task_name), timeout=timeout)
        return await asyncio.wait_for(handler(agent), timeout=timeout)
    finally:
        with contextlib.suppress(Exception):
            await agent.close()


def require_str(args: dict[str, Any], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"`{name}` must be a non-empty string")
    return value


def require_plan_steps(args: dict[str, Any]) -> list[dict[str, Any]]:
    steps = args.get("steps")
    if not isinstance(steps, list) or not all(isinstance(step, dict) for step in steps):
        raise ValueError("`steps` must be an array of action objects")
    return steps


LOCATOR_FIELDS = {
    "selector", "text", "contains", "exact_text", "placeholder",
    "label", "aria_label", "name", "role", "tag", "index",
}


def locator_from_args(args: dict[str, Any]) -> dict[str, Any]:
    locator = args.get("locator")
    if locator is None:
        locator = {key: args[key] for key in LOCATOR_FIELDS if key in args}
    if not isinstance(locator, dict) or not locator:
        raise ValueError("Provide a locator or one of the supported locator fields")
    return locator


def interaction_mode(args: dict[str, Any]) -> str:
    mode = args.get("mode", "smart")
    if mode not in {"smart", "direct"}:
        raise ValueError("`mode` must be `smart` or `direct`")
    return mode


def ensure_snapshot_allows_interaction(snapshot: dict[str, Any]) -> None:
    if snapshot.get("blocked_by_login"):
        raise RuntimeError("Login or verification wall detected. Ask the user to handle it manually.")
    if snapshot.get("blocked_by_risk"):
        reason = snapshot.get("blocker_reason") or "site risk-control warning"
        raise RuntimeError(f"Site risk-control warning detected ({reason}). Stop automatic interaction and wait.")


async def tool_status(args: dict[str, Any]) -> dict[str, Any]:
    async def ping(agent: BrowserAgent) -> dict[str, Any]:
        return await agent._send_command("ping")

    try:
        await with_agent(ping, timeout=10)
        return ok({"connected": True, "extension_connected": True})
    except Exception as exc:
        return ok(
            {
                "connected": False,
                "extension_connected": False,
                "error": str(exc),
                "hint": "Start server_live.py and make sure the Chrome extension is connected.",
            }
        )


async def tool_capabilities(args: dict[str, Any]) -> dict[str, Any]:
    return ok(
        {
            "bridge": {
                "server": "server_live.py",
                "port": 8765,
                "python_client_url": "ws://localhost:8765/client",
                "chrome_extension_url": "ws://localhost:8765",
                "routing_rule": "Only Python/SDK/MCP clients use /client. The Chrome extension uses the root path.",
            },
            "mcp_tools": sorted(TOOLS.keys()),
            "action_plan_actions": [
                "navigate",
                "reload",
                "set_visibility",
                "snapshot",
                "observe",
                "screenshot",
                "visual_snapshot",
                "click",
                "type",
                "hover",
                "press",
                "select_option",
                "wait",
                "wait_for",
                "scroll",
                "extract",
                "evaluate",
                "checkpoint",
                "auto_operate",
            ],
            "locator_fields": [
                "selector",
                "text",
                "contains",
                "exact_text",
                "placeholder",
                "label",
                "aria_label",
                "name",
                "role",
                "tag",
                "index",
            ],
            "hard_limits": [
                "No automatic CAPTCHA, slider, login, payment, or account-risk bypass.",
                "Domain-specific pacing is enforced for Xiaohongshu, Taobao/Tmall/Xianyu/1688, and JD. Do not work around it with parallel tabs or retry loops.",
                "If snapshot reports blocked_by_login or blocked_by_risk, stop automatic interaction and preserve the page for the user.",
                "A screenshot only captures pixels; it does not interpret them unless the calling AI or host reads the image.",
                "If the caller has no vision model, use visual_snapshot for JSON layout evidence instead of relying on screenshot interpretation.",
                "A successful click/type means the bridge executed the action, not that the business goal is complete. Verify with snapshot, screenshot, extract, or page state.",
                "Do not invent unsupported actions or tool names. Use nodex_run_action_plan for multi-step flows.",
                "Use nodex_auto_operate for unfamiliar sites when the caller needs the guarded observe-plan-act-verify loop.",
            ],
        }
    )


async def tool_init(args: dict[str, Any]) -> dict[str, Any]:
    task_name = args.get("task_name", "NodeX Chrome Agent")
    if not isinstance(task_name, str) or not task_name:
        raise ValueError("`task_name` must be a non-empty string")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.init(task_name)

    return ok(await with_agent(run))


async def tool_navigate(args: dict[str, Any]) -> dict[str, Any]:
    url = require_str(args, "url")
    task_name = args.get("task_name")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.navigate(url)

    return ok(await with_agent(run, init_task_name=task_name if isinstance(task_name, str) else None))


async def tool_snapshot(args: dict[str, Any]) -> dict[str, Any]:
    async def run(agent: BrowserAgent) -> Any:
        return await agent.snapshot()

    return ok(await with_agent(run))


async def tool_observe(args: dict[str, Any]) -> dict[str, Any]:
    limit = args.get("limit", 80)
    screenshot_path = args.get("screenshot_path")
    full_page = args.get("full_page", False)
    if not isinstance(limit, int):
        raise ValueError("`limit` must be an integer")
    if screenshot_path is not None and (not isinstance(screenshot_path, str) or not screenshot_path):
        raise ValueError("`screenshot_path` must be a non-empty string when provided")
    if not isinstance(full_page, bool):
        raise ValueError("`full_page` must be a boolean")

    async def run(agent: BrowserAgent) -> Any:
        snapshot = await agent.snapshot()
        visual = await agent.visual_snapshot(limit=limit)
        result = {"snapshot": snapshot, "visual_snapshot": visual}
        if screenshot_path:
            screenshot = await agent.screenshot(screenshot_path, full_page=full_page)
            result["screenshot"] = {key: value for key, value in screenshot.items() if key != "base64"}
        return result

    return ok(await with_agent(run, timeout=90))


async def tool_hover(args: dict[str, Any]) -> dict[str, Any]:
    locator = locator_from_args(args)

    async def run(agent: BrowserAgent) -> Any:
        ensure_snapshot_allows_interaction(await agent.snapshot())
        executor = UniversalActionExecutor(agent)
        selector = await executor.resolve_selector(locator)
        return await agent.hover(selector)

    return ok(await with_agent(run))


async def tool_click(args: dict[str, Any]) -> dict[str, Any]:
    locator = locator_from_args(args)
    mode = interaction_mode(args)

    async def run(agent: BrowserAgent) -> Any:
        ensure_snapshot_allows_interaction(await agent.snapshot())
        executor = UniversalActionExecutor(agent)
        selector = await executor.resolve_selector(locator)
        result = await agent.click(selector, mode=mode)
        return {"selector": selector, "action_result": result, "verification_required": True}

    return ok(await with_agent(run))


async def tool_type(args: dict[str, Any]) -> dict[str, Any]:
    locator_args = dict(args)
    locator_args.pop("text", None)
    locator = locator_from_args(locator_args)
    text = require_str(args, "text")
    mode = interaction_mode(args)
    submit = args.get("submit", False)
    if not isinstance(submit, bool):
        raise ValueError("`submit` must be a boolean")

    async def run(agent: BrowserAgent) -> Any:
        ensure_snapshot_allows_interaction(await agent.snapshot())
        executor = UniversalActionExecutor(agent)
        selector = await executor.resolve_selector(locator)
        result = await agent.type(selector, text, mode=mode, submit=submit)
        return {"selector": selector, "submitted": submit, "action_result": result, "verification_required": True}

    return ok(await with_agent(run))


async def tool_press(args: dict[str, Any]) -> dict[str, Any]:
    key = require_str(args, "key")

    async def run(agent: BrowserAgent) -> Any:
        ensure_snapshot_allows_interaction(await agent.snapshot())
        return await agent.press(key)

    return ok(await with_agent(run))


async def tool_select_option(args: dict[str, Any]) -> dict[str, Any]:
    locator = locator_from_args(args)
    provided = [args.get("value") is not None, args.get("option_label") is not None, args.get("option_index") is not None]
    if sum(provided) != 1:
        raise ValueError("Provide exactly one of value, option_label, or option_index")

    async def run(agent: BrowserAgent) -> Any:
        ensure_snapshot_allows_interaction(await agent.snapshot())
        executor = UniversalActionExecutor(agent)
        selector = await executor.resolve_selector(locator)
        result = await agent.select_option(
            selector,
            value=args.get("value"),
            label=args.get("option_label"),
            index=args.get("option_index"),
        )
        return {"selector": selector, "action_result": result, "verification_required": True}

    return ok(await with_agent(run))


async def tool_reload(args: dict[str, Any]) -> dict[str, Any]:
    async def run(agent: BrowserAgent) -> Any:
        ensure_snapshot_allows_interaction(await agent.snapshot())
        return await agent.reload()

    return ok(await with_agent(run, timeout=90))


async def tool_set_visibility(args: dict[str, Any]) -> dict[str, Any]:
    visible = args.get("visible", False)
    if not isinstance(visible, bool):
        raise ValueError("`visible` must be a boolean")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.set_visibility(visible)

    return ok(await with_agent(run))


async def tool_tabs(args: dict[str, Any]) -> dict[str, Any]:
    async def run(agent: BrowserAgent) -> Any:
        return {"active": await agent.active_tab(), "tabs": await agent.list_tabs()}

    return ok(await with_agent(run))


async def tool_claim_tab(args: dict[str, Any]) -> dict[str, Any]:
    tab_id = args.get("tab_id")
    if not isinstance(tab_id, int):
        raise ValueError("`tab_id` must be an integer returned by nodex_tabs")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.claim_tab(tab_id)

    return ok(await with_agent(run))


async def tool_close_tab(args: dict[str, Any]) -> dict[str, Any]:
    tab_id = args.get("tab_id")
    if not isinstance(tab_id, int):
        raise ValueError("`tab_id` must be an integer returned by nodex_tabs")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.close_tab(tab_id)

    return ok(await with_agent(run))


async def tool_scroll(args: dict[str, Any]) -> dict[str, Any]:
    x = args.get("x", 0)
    y = args.get("y", 0)
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ValueError("`x` and `y` must be numbers")

    async def run(agent: BrowserAgent) -> Any:
        ensure_snapshot_allows_interaction(await agent.snapshot())
        result = await agent.evaluate(f"window.scrollBy({float(x)}, {float(y)}); ({{x: window.scrollX, y: window.scrollY}})")
        return {"position": result, "verification_required": True}

    return ok(await with_agent(run))


async def tool_evaluate(args: dict[str, Any]) -> dict[str, Any]:
    code = require_str(args, "code")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.evaluate(code)

    return ok(await with_agent(run))


async def tool_screenshot(args: dict[str, Any]) -> dict[str, Any]:
    path = args.get("path")
    full_page = args.get("full_page", args.get("fullPage", False))
    if path is not None and (not isinstance(path, str) or not path):
        raise ValueError("`path` must be a non-empty string when provided")
    if not isinstance(full_page, bool):
        raise ValueError("`full_page` must be a boolean when provided")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.screenshot(path, full_page=full_page)

    return ok(await with_agent(run))


async def tool_visual_snapshot(args: dict[str, Any]) -> dict[str, Any]:
    limit = args.get("limit", 80)
    if not isinstance(limit, int):
        raise ValueError("`limit` must be an integer when provided")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.visual_snapshot(limit=limit)

    return ok(await with_agent(run))


async def tool_download(args: dict[str, Any]) -> dict[str, Any]:
    url = require_str(args, "url")
    filename = args.get("filename")
    if filename is not None and (not isinstance(filename, str) or not filename):
        raise ValueError("`filename` must be a non-empty string when provided")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.download(url, filename)

    return ok(await with_agent(run))


async def tool_run_action_plan(args: dict[str, Any]) -> dict[str, Any]:
    steps = require_plan_steps(args)
    group_name = args.get("group_name", "NodeX Action Plan")
    stop_on_error = args.get("stop_on_error", True)
    if not isinstance(group_name, str) or not group_name:
        raise ValueError("`group_name` must be a non-empty string")
    if not isinstance(stop_on_error, bool):
        raise ValueError("`stop_on_error` must be a boolean")

    plan = {
        "group_name": group_name,
        "stop_on_error": stop_on_error,
        "steps": steps,
    }
    executor = UniversalActionExecutor()
    result = await asyncio.wait_for(executor.run_plan_data(plan), timeout=300)
    return ok(result)


async def tool_auto_operate(args: dict[str, Any]) -> dict[str, Any]:
    goal = require_str(args, "goal")
    url = args.get("url")
    if url is not None and (not isinstance(url, str) or not url):
        raise ValueError("`url` must be a non-empty string when provided")

    max_rounds = args.get("max_rounds", 4)
    if not isinstance(max_rounds, int) or max_rounds < 1 or max_rounds > 12:
        raise ValueError("`max_rounds` must be an integer from 1 to 12")

    output_file = args.get("output_file", str(ROOT / "auto_operator_report.json"))
    if not isinstance(output_file, str) or not output_file:
        raise ValueError("`output_file` must be a non-empty string")

    take_screenshots = args.get("take_screenshots", False)
    if not isinstance(take_screenshots, bool):
        raise ValueError("`take_screenshots` must be a boolean")

    config = AutoOperatorConfig(
        goal=goal,
        url=url,
        max_rounds=max_rounds,
        output_file=output_file,
        take_screenshots=take_screenshots,
        screenshot_dir=str(ROOT / "debug" / "auto_operator"),
        persist_report="output_file" in args,
    )
    result = await asyncio.wait_for(AutoOperator(config).run(), timeout=420)
    return ok(result)


TOOLS: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    "nodex_capabilities": tool_capabilities,
    "nodex_status": tool_status,
    "nodex_init": tool_init,
    "nodex_navigate": tool_navigate,
    "nodex_reload": tool_reload,
    "nodex_set_visibility": tool_set_visibility,
    "nodex_tabs": tool_tabs,
    "nodex_claim_tab": tool_claim_tab,
    "nodex_close_tab": tool_close_tab,
    "nodex_snapshot": tool_snapshot,
    "nodex_observe": tool_observe,
    "nodex_hover": tool_hover,
    "nodex_click": tool_click,
    "nodex_type": tool_type,
    "nodex_press": tool_press,
    "nodex_select_option": tool_select_option,
    "nodex_scroll": tool_scroll,
    "nodex_evaluate": tool_evaluate,
    "nodex_screenshot": tool_screenshot,
    "nodex_visual_snapshot": tool_visual_snapshot,
    "nodex_download": tool_download,
    "nodex_run_action_plan": tool_run_action_plan,
    "nodex_auto_operate": tool_auto_operate,
}


LOCATOR_SCHEMA_PROPERTIES = {
    "locator": {"type": "object", "description": "Semantic locator object."},
    "selector": {"type": "string"},
    "text": {"type": "string"},
    "contains": {"type": "string"},
    "exact_text": {"type": "string"},
    "placeholder": {"type": "string"},
    "label": {"type": "string"},
    "aria_label": {"type": "string"},
    "name": {"type": "string"},
    "role": {"type": "string"},
    "tag": {"type": "string"},
    "index": {"type": "integer"},
}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "nodex_capabilities",
        "description": "Return the exact NodeX bridge routes, MCP tools, supported action-plan actions, locator fields, and hard safety/verification limits. Call this when unsure instead of inventing tools or actions.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "nodex_status",
        "description": "Check whether the local NodeX bridge and Chrome extension are reachable.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "nodex_init",
        "description": "Create or attach the controlled Chrome tab group.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_name": {"type": "string"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_navigate",
        "description": "Navigate the controlled Chrome tab to a URL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "task_name": {"type": "string"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_reload",
        "description": "Reload the controlled tab and wait for page loading to complete.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "nodex_set_visibility",
        "description": "Keep NodeX browser work in the background by default, or explicitly bring its tab forward for visible demonstrations.",
        "inputSchema": {
            "type": "object",
            "properties": {"visible": {"type": "boolean"}},
            "required": ["visible"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_tabs",
        "description": "List Chrome tabs and the currently active tab. Use returned tab ids only with nodex_claim_tab or nodex_close_tab.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "nodex_claim_tab",
        "description": "Explicitly claim an HTTP/HTTPS Chrome tab returned by nodex_tabs.",
        "inputSchema": {
            "type": "object",
            "properties": {"tab_id": {"type": "integer"}},
            "required": ["tab_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_close_tab",
        "description": "Close an exact Chrome tab id returned by nodex_tabs. Do not close user tabs without explicit authorization.",
        "inputSchema": {
            "type": "object",
            "properties": {"tab_id": {"type": "integer"}},
            "required": ["tab_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_snapshot",
        "description": "Return visible page elements and login-wall detection state.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "nodex_observe",
        "description": "Collect DOM safety state plus a bounded visual-layout JSON snapshot in one call; optionally save a screenshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "screenshot_path": {"type": "string"},
                "full_page": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_hover",
        "description": "Move the visible cursor to one uniquely resolved semantic or CSS locator.",
        "inputSchema": {
            "type": "object",
            "properties": LOCATOR_SCHEMA_PROPERTIES,
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_click",
        "description": "Resolve one unique visible element and click it after a safety snapshot. The result still requires state verification.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **LOCATOR_SCHEMA_PROPERTIES,
                "mode": {"type": "string", "enum": ["smart", "direct"]},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_type",
        "description": "Replace text in one uniquely resolved input. Submission is separate and disabled unless submit=true.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **LOCATOR_SCHEMA_PROPERTIES,
                "text": {"type": "string"},
                "mode": {"type": "string", "enum": ["smart", "direct"], "description": "smart simulates typing delays; direct inserts text instantly"},
                "submit": {"type": "boolean", "description": "Press Enter after typing; defaults to false"},
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_press",
        "description": "Press a keyboard key or shortcut in the controlled tab, for example Enter or Control+A.",
        "inputSchema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_select_option",
        "description": "Select a native HTML option by value, exact label, or zero-based index after resolving one select element.",
        "inputSchema": {
            "type": "object",
            "properties": {
                **LOCATOR_SCHEMA_PROPERTIES,
                "value": {"type": "string"},
                "option_label": {"type": "string"},
                "option_index": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_scroll",
        "description": "Scroll the controlled page by x/y pixel deltas, then return the resulting scroll position.",
        "inputSchema": {
            "type": "object",
            "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_evaluate",
        "description": "Evaluate JavaScript in the controlled Chrome tab. Use only for trusted code.",
        "inputSchema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_screenshot",
        "description": "Capture a PNG screenshot of the controlled Chrome tab. Optionally save it to a local path; otherwise returns base64.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "full_page": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_visual_snapshot",
        "description": "Return a vision-model-free JSON layout summary: viewport, visible elements, bounding boxes, text, roles, selectors, z-index, and likely overlays.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_download",
        "description": "Download a URL through Chrome's downloads manager without relying on a foreground page click.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "filename": {"type": "string"},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_run_action_plan",
        "description": "Run a resilient JSON action plan through NodeX. Supports navigate, snapshot/observe, screenshot, visual_snapshot, wait_for, click/type/hover with CSS or semantic locators (text, contains, placeholder, label, aria_label, role), scroll, extract, evaluate, and checkpoint. Prefer this over generating one-off browser scripts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "group_name": {"type": "string"},
                "stop_on_error": {"type": "boolean"},
                "steps": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
            "required": ["steps"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_auto_operate",
        "description": "Run a guarded observe-plan-act-verify loop for an unfamiliar website. Performs only high-confidence generic actions, stops on safety blockers, and returns evidence plus a planner prompt when replanning is needed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "url": {"type": "string"},
                "max_rounds": {"type": "integer"},
                "output_file": {"type": "string"},
                "take_screenshots": {"type": "boolean"},
            },
            "required": ["goal"],
            "additionalProperties": False,
        },
    },
]

async def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if request_id is None:
        return None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "nodex-chrome-agent", "version": "0.2.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOL_DEFINITIONS}
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            if tool_name not in TOOLS:
                raise ValueError(f"Unknown tool: {tool_name}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
            result = await TOOLS[tool_name](arguments)
        else:
            raise ValueError(f"Unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32000, "message": str(exc)},
        }


async def main() -> None:
    os.chdir(ROOT)
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = await handle_request(request)
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
