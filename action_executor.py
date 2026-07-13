"""
Universal Web Action Plan Executor.

Runs JSON action plans against the local NodeX Chrome bridge. The executor is
intended to be the default path for common browser tasks so agents do not need
to generate one-off scripts for every website.
"""

import argparse
import asyncio
import contextlib
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


LOCATOR_KEYS = {
    "selector",
    "text",
    "contains",
    "exact_text",
    "placeholder",
    "aria_label",
    "label",
    "name",
    "role",
    "tag",
    "index",
}


class UniversalActionExecutor:
    def __init__(self, agent: BrowserAgent = None):
        self.agent = agent or BrowserAgent()
        self.extracted_data: Dict[str, Any] = {}
        self.last_snapshot: Dict[str, Any] = {}

    async def initialize(self, group_name: str = "NodeX Action Plan"):
        await self.agent.connect()
        await self.agent.init(group_name)

    async def guard_interaction(self) -> None:
        snapshot = await self.agent.snapshot()
        self.last_snapshot = snapshot
        if snapshot.get("blocked_by_login"):
            raise RuntimeError(
                "Login, CAPTCHA, or verification wall detected. Stop and ask the user to handle it manually."
            )

    def locator_from_step(self, step: Dict[str, Any]) -> Dict[str, Any]:
        locator = step.get("locator")
        if locator is None:
            locator = {key: step[key] for key in LOCATOR_KEYS if key in step}
        if not isinstance(locator, dict) or not locator:
            raise ValueError("Step needs a locator: selector, text, contains, placeholder, aria_label, label, role, or locator.")
        return locator

    async def resolve_selector(self, locator: Dict[str, Any], timeout: float = 8.0) -> str:
        deadline = asyncio.get_event_loop().time() + timeout
        last_result: Any = None
        while True:
            result = await self.agent.evaluate(self._locator_js(locator))
            last_result = result
            if isinstance(result, dict) and result.get("selector"):
                count = int(result.get("count", 1))
                if count > 1 and "index" not in locator:
                    raise RuntimeError(
                        f"Locator is ambiguous and matched {count} visible elements: {locator}. "
                        "Add a stable attribute, scope the locator, or provide an explicit index from fresh observation evidence."
                    )
                return str(result["selector"])
            if asyncio.get_event_loop().time() >= deadline:
                raise RuntimeError(f"Could not resolve locator {locator}. Last result: {last_result}")
            await asyncio.sleep(0.4)

    def _locator_js(self, locator: Dict[str, Any]) -> str:
        loc_json = json.dumps(locator, ensure_ascii=False)
        return f"""
(() => {{
  const loc = {loc_json};
  const escapeCss = (value) => {{
    if (window.CSS && CSS.escape) return CSS.escape(String(value));
    return String(value).replace(/[^a-zA-Z0-9_-]/g, (ch) => "\\\\" + ch);
  }};
  const clean = (value) => String(value || "").replace(/\\s+/g, " ").trim();
  const visible = (el) => {{
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
  }};
  const textOf = (el) => clean([el.innerText, el.value, el.placeholder, el.getAttribute("aria-label"), el.name].filter(Boolean).join(" "));
  const selectorFor = (el) => {{
    if (el.id) return "#" + escapeCss(el.id);
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body) {{
      let part = node.tagName.toLowerCase();
      if (node.getAttribute("name")) part += `[name=${{escapeCss(node.getAttribute("name"))}}]`;
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
  const matches = (el) => {{
    if (!visible(el)) return false;
    if (loc.tag && el.tagName.toLowerCase() !== String(loc.tag).toLowerCase()) return false;
    if (loc.role && String(el.getAttribute("role") || "").toLowerCase() !== String(loc.role).toLowerCase()) return false;
    if (loc.name && String(el.getAttribute("name") || "").toLowerCase() !== String(loc.name).toLowerCase()) return false;
    if (loc.placeholder && !clean(el.placeholder).toLowerCase().includes(clean(loc.placeholder).toLowerCase())) return false;
    if (loc.aria_label && !clean(el.getAttribute("aria-label")).toLowerCase().includes(clean(loc.aria_label).toLowerCase())) return false;
    const haystack = textOf(el).toLowerCase();
    if (loc.exact_text && haystack !== clean(loc.exact_text).toLowerCase()) return false;
    if (loc.text && !haystack.includes(clean(loc.text).toLowerCase())) return false;
    if (loc.contains && !haystack.includes(clean(loc.contains).toLowerCase())) return false;
    return true;
  }};

  if (loc.selector) {{
    const direct = Array.from(document.querySelectorAll(loc.selector)).filter(visible);
    const item = direct[Number(loc.index || 0)];
    if (item) return {{ selector: selectorFor(item), source: "selector", text: textOf(item), count: direct.length }};
  }}

  if (loc.label) {{
    const wanted = clean(loc.label).toLowerCase();
    const labels = Array.from(document.querySelectorAll("label")).filter(visible);
    const targets = [];
    for (const label of labels) {{
      if (!clean(label.innerText).toLowerCase().includes(wanted)) continue;
      let target = label.control || (label.htmlFor ? document.getElementById(label.htmlFor) : null);
      target = target || label.querySelector("input, textarea, select, [contenteditable='true']");
      if (target && visible(target)) targets.push(target);
    }}
    const target = targets[Number(loc.index || 0)];
    if (target) return {{ selector: selectorFor(target), source: "label", text: textOf(target), count: targets.length }};
  }}

  const query = [
    "a", "button", "input", "textarea", "select", "summary",
    "[role]", "[contenteditable='true']", "[tabindex]",
    "h1", "h2", "h3", "h4", "span", "div"
  ].join(",");
  const candidates = Array.from(document.querySelectorAll(query)).filter(matches);
  candidates.sort((a, b) => {{
    const score = (el) => /^(BUTTON|A|INPUT|TEXTAREA|SELECT)$/.test(el.tagName) ? 0 : 1;
    return score(a) - score(b);
  }});
  const item = candidates[Number(loc.index || 0)];
  return item ? {{ selector: selectorFor(item), source: "semantic", text: textOf(item), count: candidates.length }} : {{ selector: null, count: 0 }};
}})()
"""

    async def wait_for_condition(self, step: Dict[str, Any]) -> Any:
        timeout = float(step.get("timeout", 15))
        deadline = asyncio.get_event_loop().time() + timeout
        last_value: Any = None
        locator_wait_keys = LOCATOR_KEYS - {"text", "contains", "index"}
        while True:
            if "locator" in step or any(key in step for key in locator_wait_keys):
                try:
                    selector = await self.resolve_selector(self.locator_from_step(step), timeout=0.5)
                    return {"selector": selector}
                except Exception as exc:
                    last_value = str(exc)
            elif "text" in step or "contains" in step:
                needle = step.get("text", step.get("contains"))
                code = f"document.body && document.body.innerText.includes({json.dumps(str(needle), ensure_ascii=False)})"
                last_value = await self.agent.evaluate(code)
                if last_value:
                    return True
            elif "js" in step:
                last_value = await self.agent.evaluate(step["js"])
                if last_value:
                    return last_value
            else:
                raise ValueError("wait_for requires selector/locator, text/contains, or js.")

            if asyncio.get_event_loop().time() >= deadline:
                raise TimeoutError(f"Timed out waiting for condition. Last value: {last_value}")
            await asyncio.sleep(float(step.get("interval", 0.5)))

    async def execute_step_once(self, step: Dict[str, Any], step_idx: int) -> Any:
        action = step.get("action")
        logging.info("[Step %s] Executing action: %s", step_idx, action)

        if action == "navigate":
            url = step.get("url")
            if not url:
                raise ValueError("Missing url for navigate action.")
            result = await self.agent.navigate(url)
            if step.get("wait_seconds") is not None:
                await asyncio.sleep(float(step["wait_seconds"]))
            return result

        if action in ("snapshot", "observe"):
            snapshot = await self.agent.snapshot()
            self.last_snapshot = snapshot
            key = step.get("key", f"snapshot_{step_idx}")
            self.extracted_data[key] = snapshot
            return snapshot

        if action == "screenshot":
            path = step.get("path")
            full_page = bool(step.get("full_page", step.get("fullPage", False)))
            result = await self.agent.screenshot(path, full_page=full_page)
            key = step.get("key", f"screenshot_{step_idx}")
            self.extracted_data[key] = {
                item_key: item_value
                for item_key, item_value in result.items()
                if item_key != "base64" or not path
            }
            return result

        if action == "visual_snapshot":
            limit = int(step.get("limit", 80))
            result = await self.agent.visual_snapshot(limit=limit)
            key = step.get("key", f"visual_snapshot_{step_idx}")
            self.extracted_data[key] = result
            return result

        if action == "click":
            if step.get("safe", True):
                await self.guard_interaction()
            selector = await self.resolve_selector(self.locator_from_step(step), float(step.get("timeout", 8)))
            mode = step.get("mode", "smart")
            return await self.agent.click(selector, mode=mode)

        if action == "type":
            if step.get("safe", True):
                await self.guard_interaction()
            text = step.get("value", step.get("text_to_type", step.get("input")))
            if text is None and "selector" in step and "text" in step:
                text = step.get("text")
            if text is None:
                raise ValueError("Missing value/text_to_type/input for type action.")
            locator = {"selector": step["selector"]} if "selector" in step and "locator" not in step else self.locator_from_step(step)
            selector = await self.resolve_selector(locator, float(step.get("timeout", 8)))
            return await self.agent.type(
                selector,
                str(text),
                mode=step.get("mode", "smart"),
                submit=bool(step.get("submit", False)),
            )

        if action == "hover":
            selector = await self.resolve_selector(self.locator_from_step(step), float(step.get("timeout", 8)))
            return await self.agent.hover(selector)

        if action == "press":
            key = step.get("key")
            if not isinstance(key, str) or not key:
                raise ValueError("Missing key for press action.")
            return await self.agent.press(key)

        if action == "select_option":
            if step.get("safe", True):
                await self.guard_interaction()
            selector = await self.resolve_selector(self.locator_from_step(step), float(step.get("timeout", 8)))
            return await self.agent.select_option(
                selector,
                value=step.get("value"),
                label=step.get("option_label"),
                index=step.get("option_index"),
            )

        if action == "reload":
            return await self.agent.reload()

        if action == "set_visibility":
            visible = step.get("visible", False)
            if not isinstance(visible, bool):
                raise ValueError("set_visibility requires a boolean visible field.")
            return await self.agent.set_visibility(visible)

        if action == "wait":
            seconds = float(step.get("seconds", 2))
            await asyncio.sleep(seconds)
            return True

        if action == "wait_for":
            return await self.wait_for_condition(step)

        if action == "scroll":
            direction = step.get("direction", "down")
            amount = int(step.get("amount", 800))
            repeat = int(step.get("repeat", 1))
            dy = -amount if direction == "up" else amount
            for _ in range(repeat):
                await self.agent.evaluate(f"window.scrollBy(0, {dy})")
                await asyncio.sleep(float(step.get("pause", 0.4)))
            return True

        if action == "evaluate":
            code = step.get("code")
            if not code:
                raise ValueError("Missing code for evaluate action.")
            return await self.agent.evaluate(code)

        if action == "extract":
            key = step.get("key", f"extracted_{step_idx}")
            if step.get("js_extractor"):
                result = await self.agent.evaluate(step["js_extractor"])
            else:
                locator = self.locator_from_step(step)
                selector = await self.resolve_selector(locator, float(step.get("timeout", 8)))
                result = await self.agent.evaluate(
                    f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return null;
  return {{
    text: (el.innerText || el.value || el.getAttribute("aria-label") || "").trim(),
    href: el.href || null,
    src: el.src || null
  }};
}})()
"""
                )
            self.extracted_data[key] = result
            return result

        if action == "checkpoint":
            path = step.get("path", "task_checkpoint.json")
            data = {
                "note": step.get("note", ""),
                "last_snapshot": self.last_snapshot,
                "extracted_data": self.extracted_data,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {"path": path}

        raise ValueError(f"Unknown action type: {action}")

    async def execute_step(self, step: Dict[str, Any], step_idx: int) -> Any:
        retries = int(step.get("retries", 1))
        last_error: Optional[Exception] = None
        for attempt in range(1, retries + 1):
            try:
                return await self.execute_step_once(step, step_idx)
            except Exception as exc:
                last_error = exc
                logging.warning("[Step %s] Attempt %s/%s failed: %s", step_idx, attempt, retries, exc)
                if attempt < retries:
                    with contextlib.suppress(Exception):
                        self.last_snapshot = await self.agent.snapshot()
                    await asyncio.sleep(float(step.get("retry_delay", 1.0)))
        raise last_error or RuntimeError("Step failed")

    async def run_plan(self, plan_path: str):
        logging.info("Starting NodeX action plan: %s", plan_path)

        if not os.path.exists(plan_path):
            raise FileNotFoundError(f"Action plan file not found: {plan_path}")

        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)

        plan = dict(plan)
        plan.setdefault(
            "output_file",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "action_execution_report.json"),
        )
        return await self.run_plan_data(plan)

    async def run_plan_data(self, plan: Dict[str, Any]):
        """Execute an in-memory plan; report persistence is opt-in via output_file."""
        if not isinstance(plan, dict):
            raise ValueError("Action plan must be an object.")

        group_name = plan.get("group_name", "NodeX Action Plan")
        steps = plan.get("steps", [])
        if not isinstance(steps, list):
            raise ValueError("Plan field steps must be a list.")
        if not all(isinstance(step, dict) for step in steps):
            raise ValueError("Every action plan step must be an object.")

        self.extracted_data = {}
        self.last_snapshot = {}

        await self.initialize(group_name)

        report: List[Dict[str, Any]] = []
        try:
            for idx, step in enumerate(steps, 1):
                try:
                    result = await self.execute_step(step, idx)
                    report.append({"step": idx, "action": step.get("action"), "status": "success", "result": result})
                except Exception as exc:
                    logging.error("Error at step %s (%s): %s", idx, step.get("action"), exc)
                    report.append({"step": idx, "action": step.get("action"), "status": "failed", "error": str(exc)})
                    if plan.get("stop_on_error", True):
                        break
        finally:
            await self.agent.close()

        mutating_actions = {"navigate", "reload", "click", "type", "press", "select_option", "scroll", "evaluate"}
        evidence_actions = {"snapshot", "observe", "screenshot", "visual_snapshot", "wait_for", "extract", "checkpoint"}
        successful = [item for item in report if item.get("status") == "success"]
        last_mutation = max(
            (index for index, item in enumerate(successful) if item.get("action") in mutating_actions),
            default=-1,
        )
        post_action_evidence = [
            item.get("action")
            for index, item in enumerate(successful)
            if index > last_mutation and item.get("action") in evidence_actions
        ]
        failed = any(item.get("status") == "failed" for item in report)
        if last_mutation < 0:
            evidence_status = "not_required"
        elif post_action_evidence:
            evidence_status = "present"
        else:
            evidence_status = "missing"

        output_data = {
            "group_name": group_name,
            "execution_steps": report,
            "extracted_data": self.extracted_data,
            "verification": {
                "status": evidence_status,
                "post_action_evidence": post_action_evidence,
                "has_failed_steps": failed,
                "completion_claim": "review_evidence" if evidence_status == "present" and not failed else "not_verified",
                "note": "Successful browser actions are not proof that the user's business goal completed.",
            },
        }
        output_file = plan.get("output_file")
        if output_file:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
            logging.info("Action plan completed. Report saved at: %s", output_file)
        else:
            logging.info("Action plan completed in memory.")
        return output_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Web Action Flow Executor")
    parser.add_argument("--plan", required=True, help="Path to JSON action plan file")
    args = parser.parse_args()

    executor = UniversalActionExecutor()
    asyncio.run(executor.run_plan(args.plan))
