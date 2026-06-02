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


PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT = 45


def text_content(value: Any) -> list[dict[str, str]]:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    return [{"type": "text", "text": text}]


def ok(value: Any) -> dict[str, Any]:
    return {"content": text_content(value)}


def error(value: Any) -> dict[str, Any]:
    return {"content": text_content(value), "isError": True}


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


async def tool_hover(args: dict[str, Any]) -> dict[str, Any]:
    selector = require_str(args, "selector")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.hover(selector)

    return ok(await with_agent(run))


async def tool_click(args: dict[str, Any]) -> dict[str, Any]:
    selector = require_str(args, "selector")

    async def run(agent: BrowserAgent) -> Any:
        snapshot = await agent.snapshot()
        if snapshot.get("blocked_by_login"):
            raise RuntimeError("Login or verification wall detected. Ask the user to handle it manually.")
        return await agent.click(selector)

    return ok(await with_agent(run))


async def tool_type(args: dict[str, Any]) -> dict[str, Any]:
    selector = require_str(args, "selector")
    text = require_str(args, "text")

    async def run(agent: BrowserAgent) -> Any:
        snapshot = await agent.snapshot()
        if snapshot.get("blocked_by_login"):
            raise RuntimeError("Login or verification wall detected. Ask the user to handle it manually.")
        return await agent.type(selector, text)

    return ok(await with_agent(run))


async def tool_evaluate(args: dict[str, Any]) -> dict[str, Any]:
    code = require_str(args, "code")

    async def run(agent: BrowserAgent) -> Any:
        return await agent.evaluate(code)

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

    plan_path = ROOT / ".nodex_mcp_action_plan.json"
    plan = {
        "group_name": group_name,
        "stop_on_error": stop_on_error,
        "steps": steps,
    }
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        executor = UniversalActionExecutor()
        result = await asyncio.wait_for(executor.run_plan(str(plan_path)), timeout=300)
        return ok(result)
    finally:
        with contextlib.suppress(OSError):
            plan_path.unlink()


TOOLS: dict[str, Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]] = {
    "nodex_status": tool_status,
    "nodex_init": tool_init,
    "nodex_navigate": tool_navigate,
    "nodex_snapshot": tool_snapshot,
    "nodex_hover": tool_hover,
    "nodex_click": tool_click,
    "nodex_type": tool_type,
    "nodex_evaluate": tool_evaluate,
    "nodex_download": tool_download,
    "nodex_run_action_plan": tool_run_action_plan,
}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
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
        "name": "nodex_snapshot",
        "description": "Return visible page elements and login-wall detection state.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "nodex_hover",
        "description": "Move the visible cursor to a CSS selector.",
        "inputSchema": {
            "type": "object",
            "properties": {"selector": {"type": "string"}},
            "required": ["selector"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_click",
        "description": "Click a CSS selector after checking for login or verification walls.",
        "inputSchema": {
            "type": "object",
            "properties": {"selector": {"type": "string"}},
            "required": ["selector"],
            "additionalProperties": False,
        },
    },
    {
        "name": "nodex_type",
        "description": "Type text into a CSS selector after checking for login or verification walls.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["selector", "text"],
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
        "description": "Run a sequential JSON action plan through the NodeX action executor.",
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
                "serverInfo": {"name": "nodex-chrome-agent", "version": "0.1.0"},
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
