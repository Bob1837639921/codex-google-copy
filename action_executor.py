"""
Universal Web Action Plan Executor (通用网页动作流执行引擎)
========================================================================
A highly resilient, general-purpose browser executor that reads sequential
action plans (navigating, typing, clicking, waiting, custom extracting, 
and JS evaluations) and executes them on the active Chrome instance via CDP.

Supports form filling, web scraping, data extraction, and multi-page workflows.

Author: Antigravity Team
Date: 2026-06-01
License: MIT
"""

import sys
import os
import asyncio
import logging
import json
import argparse
from typing import Dict, List, Any

# Ensure workspace is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class UniversalActionExecutor:
    def __init__(self):
        self.agent = BrowserAgent()
        self.extracted_data = {}

    async def initialize(self, group_name: str = "AI 智能控制流"):
        await self.agent.connect()
        await self.agent.init(group_name)

    async def execute_step(self, step: Dict[str, Any], step_idx: int) -> Any:
        action = step.get("action")
        logging.info(f"[Step {step_idx}] Executing Action: '{action}'")
        
        if action == "navigate":
            url = step.get("url")
            if not url:
                raise ValueError("Missing 'url' parameter for navigate action.")
            logging.info(f" -> Navigating to: {url}")
            return await self.agent.navigate(url)
            
        elif action == "click":
            selector = step.get("selector")
            if not selector:
                raise ValueError("Missing 'selector' parameter for click action.")
            logging.info(f" -> Clicking element: {selector}")
            return await self.agent.click(selector)
            
        elif action == "type":
            selector = step.get("selector")
            text = step.get("text")
            if not selector or text is None:
                raise ValueError("Missing 'selector' or 'text' parameter for type action.")
            logging.info(f" -> Typing into '{selector}': '{text}'")
            return await self.agent.type(selector, text)
            
        elif action == "hover":
            selector = step.get("selector")
            if not selector:
                raise ValueError("Missing 'selector' parameter for hover action.")
            logging.info(f" -> Hovering over: {selector}")
            return await self.agent.hover(selector)
            
        elif action == "wait":
            seconds = step.get("seconds", 2)
            logging.info(f" -> Waiting for {seconds} seconds...")
            await asyncio.sleep(seconds)
            return True
            
        elif action == "evaluate":
            code = step.get("code")
            if not code:
                raise ValueError("Missing 'code' parameter for evaluate action.")
            logging.info(" -> Evaluating custom script...")
            return await self.agent.evaluate(code)
            
        elif action == "extract":
            key = step.get("key", f"extracted_{step_idx}")
            js_extractor = step.get("js_extractor")
            if not js_extractor:
                raise ValueError("Missing 'js_extractor' JS script parameter for extract action.")
            logging.info(f" -> Extracting data into key: '{key}'")
            res = await self.agent.evaluate(js_extractor)
            self.extracted_data[key] = res
            logging.info(f" -> Extracted value: {res}")
            return res
            
        elif action == "snapshot":
            logging.info(" -> Taking DOM snapshot...")
            snap = await self.agent.snapshot()
            self.extracted_data[f"snapshot_{step_idx}"] = snap
            return snap
            
        else:
            raise ValueError(f"Unknown action type: '{action}'")

    async def run_plan(self, plan_path: str):
        logging.info("================================================================")
        logging.info(f"🏁 Starting General-Purpose Web Automation Plan: {plan_path}")
        logging.info("================================================================")
        
        if not os.path.exists(plan_path):
            raise FileNotFoundError(f"Action plan file not found: {plan_path}")
            
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
            
        group_name = plan.get("group_name", "AI 智能执行流")
        steps = plan.get("steps", [])
        
        # 1. Initialize Chrome Tab
        await self.initialize(group_name)
        
        # 2. Sequential Execution
        report = []
        for idx, step in enumerate(steps, 1):
            try:
                res = await self.execute_step(step, idx)
                report.append({
                    "step": idx,
                    "action": step.get("action"),
                    "status": "success",
                    "result": res
                })
            except Exception as e:
                logging.error(f"❌ Error at Step {idx} ({step.get('action')}): {e}")
                report.append({
                    "step": idx,
                    "action": step.get("action"),
                    "status": "failed",
                    "error": str(e)
                })
                if plan.get("stop_on_error", True):
                    logging.warning("Halting execution pipeline due to 'stop_on_error' flag.")
                    break
        
        # 3. Write Execution Output & Extracted Data
        output_data = {
            "group_name": group_name,
            "execution_steps": report,
            "extracted_data": self.extracted_data
        }
        # Write report to local directory
        output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "action_execution_report.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
            
        logging.info("================================================================")
        logging.info(f"🏆 Automation plan completed! Report saved at: {output_file}")
        logging.info("================================================================")
        
        await self.agent.close()
        return output_data

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Web Action Flow Executor")
    parser.add_argument("--plan", required=True, help="Path to JSON action plan file")
    args = parser.parse_args()
    
    executor = UniversalActionExecutor()
    asyncio.run(executor.run_plan(args.plan))
