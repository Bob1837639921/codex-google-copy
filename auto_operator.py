"""
NodeX Auto Operator.

Runs the observe -> plan -> act -> verify loop for unfamiliar websites without
pretending the bridge is an all-knowing browser agent. It performs only high
confidence generic actions, then stops with structured evidence when a planner
or the user needs to decide the next step.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from agent_core import BrowserAgent


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


BLOCKER_KEYWORDS = [
    "captcha",
    "verification",
    "verify",
    "login",
    "sign in",
    "password",
    "\u5b89\u5168\u9a8c\u8bc1",
    "\u4eba\u673a\u9a8c\u8bc1",
    "\u9a8c\u8bc1\u7801",
    "\u767b\u5f55",
    "\u767b\u5165",
    "\u626b\u7801",
    "\u5bc6\u7801",
    "\u652f\u4ed8",
    "\u98ce\u63a7",
]

SEARCH_HINTS = [
    "search",
    "find",
    "query",
    "keyword",
    "q",
    "\u641c\u7d22",
    "\u641c",
    "\u67e5\u627e",
    "\u5173\u952e\u8bcd",
]


@dataclass
class AutoOperatorConfig:
    goal: str
    url: str | None = None
    max_rounds: int = 4
    output_file: str = "auto_operator_report.json"
    screenshot_dir: str | None = None
    take_screenshots: bool = False
    visual_limit: int = 120
    task_name: str = "NodeX Auto Operator"


class AutoOperator:
    def __init__(self, config: AutoOperatorConfig):
        self.config = config
        self.agent = BrowserAgent()
        self.profiles = self.load_site_profiles()
        self.report: dict[str, Any] = {
            "goal": config.goal,
            "url": config.url,
            "rounds": [],
            "status": "running",
            "final_reason": "",
        }
        self._typed_search = False
        self._scrolled = 0
        self._profile_search_loaded = False
        self._profile_extracted = False

    async def run(self) -> dict[str, Any]:
        await self.agent.connect()
        await self.agent.init(self.config.task_name)
        try:
            for round_idx in range(1, self.config.max_rounds + 1):
                observation = await self.observe(round_idx)
                blocker = self.detect_blocker(observation)
                if blocker:
                    self.finish("blocked", blocker, observation)
                    break

                action = self.plan_next(observation)
                round_record = {"round": round_idx, "observation": observation, "planned_action": action}
                self.report["rounds"].append(round_record)

                if action["action"] == "stop":
                    self.finish(action.get("status", "needs_planner"), action.get("reason", ""), observation)
                    break

                try:
                    result = await self.execute_action(action)
                    round_record["execution"] = {"status": "success", "result": result}
                except Exception as exc:
                    round_record["execution"] = {"status": "failed", "error": str(exc)}
                    repair_observation = await self.observe(round_idx, label="after_failure")
                    round_record["repair_observation"] = repair_observation
                    self.finish("needs_planner", f"Action failed and requires replanning: {exc}", repair_observation)
                    break
            else:
                observation = await self.observe(self.config.max_rounds, label="final")
                self.finish("needs_planner", "Maximum rounds reached without verified completion.", observation)
        finally:
            await self.agent.close()

        self.write_report()
        return self.report

    async def observe(self, round_idx: int, label: str = "observe") -> dict[str, Any]:
        snapshot = await self.agent.snapshot()
        visual = await self.agent.visual_snapshot(limit=self.config.visual_limit)
        screenshot_path = None
        if self.config.take_screenshots:
            screenshot_dir = Path(self.config.screenshot_dir or "debug/auto_operator")
            screenshot_dir.mkdir(parents=True, exist_ok=True)
            screenshot_path = str(screenshot_dir / f"{round_idx:02d}_{label}.png")
            await self.agent.screenshot(screenshot_path)

        return {
            "label": label,
            "snapshot": snapshot,
            "visual_snapshot": visual,
            "screenshot_path": screenshot_path,
            "planner_prompt": self.build_planner_prompt(snapshot, visual, screenshot_path),
        }

    def detect_blocker(self, observation: dict[str, Any]) -> str | None:
        snapshot = observation.get("snapshot") or {}
        if snapshot.get("blocked_by_login"):
            return "snapshot reported login or verification wall"

        visual = observation.get("visual_snapshot") or {}
        for item in visual.get("items", [])[:120]:
            if (item.get("type") or "").lower() == "password":
                return "password input detected"

        texts = [str(item.get("text") or "") for item in visual.get("overlays", [])[:20]]
        joined = "\n".join(texts).lower()
        for keyword in BLOCKER_KEYWORDS:
            if keyword.lower() in joined:
                return f"possible blocker keyword detected in overlay: {keyword}"
        return None

    def plan_next(self, observation: dict[str, Any]) -> dict[str, Any]:
        visual = observation.get("visual_snapshot") or {}
        current_url = ((visual.get("viewport") or {}).get("url") or "").strip()
        profile = self.match_profile(current_url) or self.match_profile(self.config.url or "")
        query = self.extract_search_query(self.config.goal)

        if profile and query:
            if profile.get("search_url_template") and not self._profile_search_loaded:
                url = profile["search_url_template"].format(query=quote_plus(query))
                self._profile_search_loaded = True
                return {"action": "navigate", "url": url, "wait_seconds": 4, "reason": f"site profile search for {profile['name']}"}
            if profile.get("extract_results_js") and not self._profile_extracted:
                self._profile_extracted = True
                return {
                    "action": "extract_js",
                    "key": f"{profile['name']}_results",
                    "code": profile["extract_results_js"],
                    "reason": f"site profile result extraction for {profile['name']}",
                }
            if self._profile_extracted:
                return {
                    "action": "stop",
                    "status": "completed",
                    "reason": f"site profile {profile['name']} extracted available results",
                }

        if self.config.url and not self.same_url(current_url, self.config.url):
            return {"action": "navigate", "url": self.config.url, "wait_seconds": 3, "reason": "target URL not loaded"}

        click_target = self.extract_click_target(self.config.goal)
        if click_target:
            item = self.find_text_item(visual, click_target)
            if item:
                return {
                    "action": "click",
                    "selector": item["selector"],
                    "reason": f"found visible item matching click target: {click_target}",
                }

        if query and not self._typed_search:
            search_item = self.find_search_input(visual)
            if search_item:
                return {
                    "action": "type",
                    "selector": search_item["selector"],
                    "text": query,
                    "reason": "found search-like input",
                }

        if query and self._typed_search and self._scrolled < 1:
            self._scrolled += 1
            return {"action": "scroll", "direction": "down", "amount": 900, "repeat": 1, "reason": "search submitted; inspect more results"}

        return {
            "action": "stop",
            "status": "needs_planner",
            "reason": "No high-confidence generic action found. Use planner_prompt evidence for the next 1-3 actions.",
        }

    async def execute_action(self, action: dict[str, Any]) -> Any:
        name = action["action"]
        if name == "navigate":
            result = await self.agent.navigate(action["url"])
            await asyncio.sleep(float(action.get("wait_seconds", 2)))
            return result
        if name == "click":
            await self.guard()
            return await self.agent.click(action["selector"])
        if name == "type":
            await self.guard()
            self._typed_search = True
            return await self.agent.type(action["selector"], action["text"])
        if name == "scroll":
            amount = int(action.get("amount", 800))
            repeat = int(action.get("repeat", 1))
            direction = action.get("direction", "down")
            dy = -amount if direction == "up" else amount
            for _ in range(repeat):
                await self.agent.evaluate(f"window.scrollBy(0, {dy})")
                await asyncio.sleep(0.5)
            return {"scrolled": dy * repeat}
        if name == "extract_js":
            result = await self.agent.evaluate(action["code"])
            self.report.setdefault("extracted_data", {})[action.get("key", "extracted")] = result
            return result
        raise ValueError(f"Unsupported auto action: {name}")

    async def guard(self) -> None:
        snapshot = await self.agent.snapshot()
        if snapshot.get("blocked_by_login"):
            raise RuntimeError("Login or verification wall detected before interaction.")

    def finish(self, status: str, reason: str, observation: dict[str, Any] | None = None) -> None:
        self.report["status"] = status
        self.report["final_reason"] = reason
        if observation is not None:
            self.report["final_observation"] = observation

    def write_report(self) -> None:
        output_path = Path(self.config.output_file)
        if output_path.parent:
            output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load_site_profiles(profile_dir: str = "site_profiles") -> list[dict[str, Any]]:
        root = Path(profile_dir)
        if not root.exists():
            return []
        profiles: list[dict[str, Any]] = []
        for path in sorted(root.glob("*.json")):
            try:
                profiles.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:
                logging.warning("Failed to load site profile %s: %s", path, exc)
        return profiles

    def match_profile(self, url: str) -> dict[str, Any] | None:
        lowered = (url or "").lower()
        for profile in self.profiles:
            for domain in profile.get("domains", []):
                if str(domain).lower() in lowered:
                    return profile
        return None

    def build_planner_prompt(self, snapshot: dict[str, Any], visual: dict[str, Any] | None, screenshot_path: str | None) -> str:
        visual = visual or {}
        evidence = {
            "goal": self.config.goal,
            "blocked_by_login": snapshot.get("blocked_by_login"),
            "dom_sample": (snapshot.get("dom") or [])[:40],
            "viewport": visual.get("viewport"),
            "visible_items": (visual.get("items") or [])[:40],
            "overlays": (visual.get("overlays") or [])[:10],
            "screenshot_path": screenshot_path,
        }
        return (
            "You are planning the next safe browser actions for NodeX.\n"
            "Return only JSON with 1-3 steps. Allowed actions: wait_for, click, type, scroll, extract, snapshot, visual_snapshot, screenshot.\n"
            "Use semantic locators or selectors present in the evidence. Do not bypass login, CAPTCHA, payment, or account-risk prompts.\n"
            "A successful action is not completion; include a verification step when possible.\n"
            f"Evidence:\n{json.dumps(evidence, ensure_ascii=False, indent=2)}"
        )

    @staticmethod
    def same_url(current: str, target: str) -> bool:
        if not current:
            return False
        return current.rstrip("/") == target.rstrip("/")

    @staticmethod
    def extract_search_query(goal: str) -> str | None:
        patterns = [
            r"(?:search for|look up|find)\s+(.+)",
            "(?:\u641c\u7d22|\u641c\u4e00\u4e0b|\u67e5\u627e|\u67e5\u8be2|\u627e)\\s*(.+)",
            "query\\s*[:\uff1a]\\s*(.+)",
        ]
        for candidate in AutoOperator.goal_variants(goal):
            for pattern in patterns:
                match = re.search(pattern, candidate, flags=re.IGNORECASE)
                if match:
                    return match.group(1).strip(" \u3002.!！")
        return None

    @staticmethod
    def extract_click_target(goal: str) -> str | None:
        patterns = [
            r"(?:click|press|open)\s+['\"]?([^'\"]+)['\"]?",
            "(?:\u70b9\u51fb|\u6253\u5f00|\u9009\u62e9|\u6309)\\s*[\u201c\"']?([^\u201d\"'\uff0c\u3002,.]+)",
        ]
        for candidate in AutoOperator.goal_variants(goal):
            for pattern in patterns:
                match = re.search(pattern, candidate, flags=re.IGNORECASE)
                if match:
                    target = match.group(1).strip()
                    if 1 <= len(target) <= 40:
                        return target
        return None

    @staticmethod
    def goal_variants(goal: str) -> list[str]:
        variants = [goal]
        for source, target in (("latin1", "utf-8"), ("gbk", "utf-8"), ("latin1", "gbk")):
            try:
                repaired = goal.encode(source, errors="ignore").decode(target, errors="ignore")
                if repaired and repaired not in variants:
                    variants.append(repaired)
            except Exception:
                pass
        return variants

    @staticmethod
    def find_search_input(visual: dict[str, Any]) -> dict[str, Any] | None:
        candidates = []
        for item in visual.get("items", []):
            if not item.get("selector"):
                continue
            tag = item.get("tag")
            role = (item.get("role") or "").lower()
            item_type = (item.get("type") or "").lower()
            text = (item.get("text") or "").lower()
            if tag not in ("input", "textarea") and role not in ("textbox", "searchbox"):
                continue
            score = 0
            if item_type in ("search", "text", ""):
                score += 2
            for hint in SEARCH_HINTS:
                if hint.lower() in text:
                    score += 3
            if item.get("box", {}).get("width", 0) > 120:
                score += 1
            candidates.append((score, item))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        return candidates[0][1] if candidates and candidates[0][0] > 0 else None

    @staticmethod
    def find_text_item(visual: dict[str, Any], target: str) -> dict[str, Any] | None:
        target_lower = target.lower()
        candidates = []
        for item in visual.get("items", []):
            if not item.get("selector"):
                continue
            text = (item.get("text") or "").lower()
            role = (item.get("role") or "").lower()
            tag = item.get("tag")
            if target_lower not in text:
                continue
            score = 1
            if tag in ("button", "a", "summary") or role in ("button", "link", "menuitem"):
                score += 4
            candidates.append((score, item))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        return candidates[0][1] if candidates else None


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run a guarded observe-plan-act loop for unfamiliar websites.")
    parser.add_argument("--goal", required=True, help="User goal in natural language.")
    parser.add_argument("--url", help="Optional target URL to load first.")
    parser.add_argument("--max-rounds", type=int, default=4)
    parser.add_argument("--output", default="auto_operator_report.json")
    parser.add_argument("--screenshots", action="store_true", help="Save screenshots for vision-capable review.")
    parser.add_argument("--screenshot-dir", default="debug/auto_operator")
    args = parser.parse_args()

    config = AutoOperatorConfig(
        goal=args.goal,
        url=args.url,
        max_rounds=args.max_rounds,
        output_file=args.output,
        screenshot_dir=args.screenshot_dir,
        take_screenshots=args.screenshots,
    )
    result = await AutoOperator(config).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
