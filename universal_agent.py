"""
Universal Cognitive Browser Agent Engine
========================================================================
An advanced, dynamic, context-aware browser automation and reasoning loop
integrating domain ecosystem analysis, heuristic anti-spam processing, 
and tiered product recommendation structures.

Author: Antigravity Team
Date: 2026-06-01
License: MIT
"""

import sys
import os
import asyncio
import logging
import json
import urllib.parse
import argparse
from typing import Dict, List, Any

# Ensure workspace is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class UniversalCognitiveAgent:
    def __init__(self):
        self.agent = BrowserAgent()

    async def initialize(self):
        await self.agent.connect()
        await self.agent.init("AI 万能智能搜索")

    async def analyze_domain_ecosystem(self, target: str, context: str) -> Dict[str, Any]:
        """
        Phase 1: Deep Intent & Domain Compatibility Reasoning
        Parses current hardware/software surroundings to establish strict constraints.
        """
        logging.info(f"Analyzing domain compatibility for '{target}' with context: '{context}'")
        
        analysis = {
            "recommended_brands": [],
            "keywords": [],
            "technical_reasons": "",
            "avoid_keywords": []
        }
        
        # Heuristics rules for routers
        if "路由器" in target or "router" in target.lower():
            if "华为" in context or "huawei" in context.lower() or "be3" in context.lower():
                analysis["recommended_brands"] = ["华为", "HUAWEI", "荣耀"]
                analysis["keywords"] = ["智联", "mesh", "AX3 Pro", "AX2 Pro", "TC7001"]
                analysis["technical_reasons"] = "检测到您主路由为华为 BE3 Pro。同品牌智联组网（Hilink/Link+）支持统一SSID、Wi-Fi密码自动同步以及无缝漫游体验。非华为路由作中继时，漫游体验较差。"
                analysis["avoid_keywords"] = ["WS5200", "WS5102", "WS851"] # Older WiFi 5 models
            elif "小米" in context or "红米" in context.lower() or "redmi" in context.lower():
                analysis["recommended_brands"] = ["小米", "红米", "Redmi"]
                analysis["keywords"] = ["mesh", "AX3000", "AX6000", "AC2100"]
                analysis["technical_reasons"] = "小米/红米路由支持小米私有 Mesh 协议，支持米家 App 统一管理及自动同步，建议选择同品牌设备。"
                analysis["avoid_keywords"] = []
                
        # Heuristics rules for GPUs
        elif "显卡" in target or "gpu" in target.lower():
            if "ryzen" in context.lower() or "5600" in context:
                analysis["recommended_brands"] = ["AMD", "NVIDIA", "华硕", "微星", "七彩虹"]
                analysis["keywords"] = ["RX 6600", "GTX 1660", "RTX 3060"]
                analysis["technical_reasons"] = "Ryzen 5600X CPU完美契合中端主流甜品显卡。若选择 AMD 显卡（如 RX 6600）可开启 Smart Access Memory (SAM) 性能加速技术。"
                analysis["avoid_keywords"] = ["矿卡", "锻炼", "影驰大将", "杂牌", "假显卡"]
                
        # Fallback generic parsing
        if not analysis["recommended_brands"]:
            # Basic brand extraction
            for brand in ["苹果", "华为", "小米", "华硕", "联想", "戴尔", "索尼", "微软", "佳能"]:
                if brand in context:
                    analysis["recommended_brands"].append(brand)
            analysis["keywords"] = [target]
            analysis["technical_reasons"] = f"针对您的使用场景（{context}），我们推荐优先选择大厂及匹配对应生态的品牌（如：{', '.join(analysis['recommended_brands'])}）。"

        return analysis

    async def execute_targeted_search(self, query: str, sort_by_latest: bool = True) -> List[Dict[str, Any]]:
        """
        Phase 2 & 3: Targeted Browser Automation & Scrape
        """
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.goofish.com/search?q={encoded_query}"
        logging.info(f"Navigating to search page: {search_url}")
        await self.agent.navigate(search_url)
        await asyncio.sleep(4)
        
        if sort_by_latest:
            logging.info("Applying '最新发布' sorting rule...")
            click_js = """
                (() => {
                    const elements = Array.from(document.querySelectorAll("div, span, a, li, button"));
                    for (let el of elements) {
                        const text = (el.innerText || "").trim();
                        if (text === "最新发布" || text === "最新" || text === "最新上架") {
                            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
                            el.click();
                            return "Clicked sort button";
                        }
                    }
                    return "Sort button not found";
                })()
            """
            await self.agent.evaluate(click_js)
            await asyncio.sleep(4)
            
        snap = await self.agent.snapshot()
        
        results = []
        dom_items = snap.get("dom", [])
        
        for item in dom_items:
            if "feeds-item-wrap" in item:
                parts = item.split(" | text: ")
                if len(parts) < 2:
                    continue
                content = parts[1]
                
                if "\xa5" in content:
                    subparts = content.split("\xa5")
                    desc = subparts[0].strip()
                    price_meta = subparts[1].strip()
                    
                    price_words = price_meta.split()
                    if not price_words:
                        continue
                    price_str = price_words[0]
                    metadata = " ".join(price_words[1:]) if len(price_words) > 1 else ""
                    
                    results.append({
                        "description": desc,
                        "price": price_str,
                        "metadata": metadata
                    })
        return results

    def apply_advanced_heuristics(self, items: List[Dict[str, Any]], domain_info: Dict[str, Any], budget_min: float, budget_max: float, custom_blacklist: List[str] = None) -> List[Dict[str, Any]]:
        """
        Phase 4: Multi-Dimensional Anti-Spam Heuristic Filter
        """
        clean_items = []
        
        # Dynamic blacklist
        if custom_blacklist is not None:
            blacklist = list(custom_blacklist)
        else:
            blacklist = ["回收", "高价收", "收手机", "主板", "爆屏", "坏机", "面议", "监管机", "批量", "大量收", "烂手机"]
        
        # Exclude specific avoided model names
        blacklist.extend(domain_info.get("avoid_keywords", []))
        
        for item in items:
            desc = item["description"]
            price_str = item["price"]
            
            try:
                price_val = float(price_str)
            except ValueError:
                continue
                
            # 1. Price Bounds Filter
            if not (budget_min <= price_val <= budget_max):
                continue
                
            # 2. Recycler Blacklist Filter
            if any(kw in desc for kw in blacklist):
                continue
                
            # 3. Description Length Text-Wall Filter (spammers dump large keywords lists)
            if len(desc) > 230:
                continue
                
            # 4. Brand & Keyword Context Reinforcement
            matches_brand = False
            for brand in domain_info.get("recommended_brands", []):
                if brand.lower() in desc.lower():
                    matches_brand = True
                    break
            
            # If recommended brands exist, we favor them heavily
            if domain_info.get("recommended_brands", []) and not matches_brand:
                continue
                
            clean_items.append(item)
            
        return clean_items

    async def navigate_to_best_match(self, best_item_desc: str):
        """
        Phase 6: Visual Delivery
        Commands the active browser tab to jump directly to the detailed listing page.
        """
        logging.info(f"Locating detail link for: {best_item_desc[:30]}...")
        extract_js = f"""
            (() => {{
                const elements = Array.from(document.querySelectorAll("a"));
                for (let a of elements) {{
                    const text = a.innerText || "";
                    if (text.includes("{best_item_desc[:20]}")) {{
                        return a.href;
                    }}
                }}
                return null;
            }})()
        """
        href = await self.agent.evaluate(extract_js)
        if href:
            logging.info(f"Detail page found: {href}. Loading page in Chrome!")
            await self.agent.navigate(href)
            await asyncio.sleep(3)
            return href
        else:
            logging.warning("Detail page link could not be located on current active list.")
            return None

    async def run_pipeline(self, target: str, context: str, budget_min: float, budget_max: float, config_path: str = None):
        logging.info("================================================================")
        logging.info("🚀 Starting Universal Cognitive Browser Automation Engine Pipeline")
        logging.info("================================================================")
        
        # 1. Initialize
        await self.initialize()
        
        # 2. Check for dynamic config override
        config_data = {}
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                logging.info(f"Successfully loaded dynamic search configuration from: {config_path}")
            except Exception as e:
                logging.error(f"Error loading config file: {e}")
                
        # 3. Dynamic Reasoning Analysis
        if config_data:
            domain_info = {
                "recommended_brands": config_data.get("recommended_brands", []),
                "keywords": config_data.get("keywords", []),
                "technical_reasons": config_data.get("technical_reasons", "动态生成的技术路线理由"),
                "avoid_keywords": config_data.get("avoid_keywords", [])
            }
            search_query_str = config_data.get("search_query", f"{target}")
            budget_min = config_data.get("min_price", budget_min)
            budget_max = config_data.get("max_price", budget_max)
            custom_blacklist = config_data.get("blacklist", None)
        else:
            domain_info = await self.analyze_domain_ecosystem(target, context)
            brand_prefix = domain_info["recommended_brands"][0] if domain_info["recommended_brands"] else ""
            search_query_str = f"{brand_prefix} {target}".strip()
            custom_blacklist = None
            
        logging.info(f"Search Strategy Configured:")
        logging.info(f"  Query: {search_query_str}")
        logging.info(f"  Price Limits: ¥{budget_min} - ¥{budget_max}")
        logging.info(f"  Brand filters: {domain_info['recommended_brands']}")
        logging.info(f"  Avoid terms: {domain_info['avoid_keywords']}")
        
        # 4. Search
        raw_items = await self.execute_targeted_search(search_query_str, sort_by_latest=True)
        
        # 5. Filter out spammers
        clean_items = self.apply_advanced_heuristics(raw_items, domain_info, budget_min, budget_max, custom_blacklist)
        
        # 6. Synthesize report & open best link
        report = {
            "analysis": domain_info,
            "best_deals": clean_items[:5],
            "total_clean_found": len(clean_items)
        }
        
        best_href = None
        if clean_items:
            best_href = await self.navigate_to_best_match(clean_items[0]["description"])
            report["loaded_best_url"] = best_href
            
        # Write report to local directory
        report_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "universal_search_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            
        logging.info(f"Pipeline executed successfully. Generated report at: {report_file}")
        await self.agent.close()
        
        return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal Cognitive Secondhand Sourcing Engine")
    parser.add_argument("--target", required=True, help="Target item to find (e.g. '路由器', '显卡')")
    parser.add_argument("--context", required=True, help="User's existing equipment/needs (e.g. '自用华为be3 pro')")
    parser.add_argument("--min_price", type=float, default=30.0, help="Minimum price limit")
    parser.add_argument("--max_price", type=float, default=200.0, help="Maximum price limit")
    parser.add_argument("--config", type=str, default=None, help="Optional dynamic search config JSON path")
    
    args = parser.parse_args()
    
    agent_orchestrator = UniversalCognitiveAgent()
    asyncio.run(agent_orchestrator.run_pipeline(
        target=args.target,
        context=args.context,
        budget_min=args.min_price,
        budget_max=args.max_price,
        config_path=args.config
    ))
