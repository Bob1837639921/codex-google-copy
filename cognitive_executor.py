"""
Cognitive Web Action Executor with Interactive Pre-flight Learning
========================================================================
This executor wraps the standard browser interaction with a Completion Detection System (CDS)
AND an interactive Pre-flight Learning phase (Phase 0) that clicks and reads tutorials.
"""

import os
import sys
import json
import asyncio
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

class ActionFailedError(Exception):
    pass

class CognitiveAgentLoop:
    def __init__(self, use_llm: bool = True):
        self.agent = BrowserAgent()
        self.use_llm = use_llm
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.learned_rules = ""  

    async def initialize(self, group_name: str = "NodeX Cognitive Loop"):
        await self.agent.connect()
        await self.agent.init(group_name)

    async def pre_flight_learning(self):
        """
        Phase 0: The Ultimate Learning Protocol.
        Includes Leaf-node targeting, Window.open interception, and Hybrid Click fallback.
        """
        logging.info("====================================")
        logging.info("🧠 [Phase 0] Initiating Ultimate Interactive Pre-flight Learning Protocol...")
        
        # 1. Inject Window.open Hook to catch popups
        logging.info("🪝 Injecting window.open interceptor to catch rogue popups...")
        hook_js = """
        (() => {
            if (!window.__capturedUrls) {
                window.__capturedUrls = [];
                const originalOpen = window.open;
                window.open = function(url, target, features) {
                    window.__capturedUrls.push(url);
                    return null; // Block popup to bypass Chrome blocker
                };
            }
            return true;
        })()
        """
        await self.agent.evaluate(hook_js)
        
        # 2. Search for the deepest leaf node containing tutorial keywords
        search_js = """
        (() => {
            const keywords = ['tutorial', 'help', 'guide', 'faq', '文档', '教程', '指南', '帮助', '规则'];
            const elements = Array.from(document.querySelectorAll('*'));
            for (let el of elements) {
                if (el.children.length > 0) continue; // Leaf nodes only
                
                const text = (el.innerText || el.textContent || '').toLowerCase().trim();
                if (text.length === 0 || text.length > 15) continue;
                
                for (let kw of keywords) {
                    if (text === kw || text.includes(kw)) {
                        let target = el;
                        while (target && target !== document.body) {
                            const style = window.getComputedStyle(target);
                            if (target.tagName === 'A' || target.tagName === 'BUTTON' || target.getAttribute('role') === 'button' || style.cursor === 'pointer' || target.onclick) {
                                break;
                            }
                            target = target.parentElement;
                        }
                        if (!target || target === document.body) target = el;
                        
                        target.id = target.id || 'nodex-tutorial-btn-' + Math.floor(Math.random() * 10000);
                        
                        let href = target.href || target.getAttribute('href');
                        if (!href && target.tagName !== 'A') {
                            const childA = target.querySelector('a');
                            if (childA) href = childA.href || childA.getAttribute('href');
                        }
                        
                        return { text: text, tag: target.tagName, selector: '#' + target.id, href: href };
                    }
                }
            }
            return null;
        })()
        """
        target_doc = await self.agent.evaluate(search_js)
        
        if target_doc and target_doc.get("selector"):
            logging.info(f"🔍 Found EXACT tutorial button: '{target_doc['text']}' -> {target_doc['selector']}")
            
            target_url = target_doc.get("href")
            
            # 3. Trigger Click if no direct href
            if target_url:
                logging.info(f"🔗 Button has direct URL: {target_url}")
            else:
                logging.info("👆 Tier 1: Dispatching native JS Synthetic Click (isTrusted=false)...")
                click_js = f"""
                (() => {{
                    const el = document.querySelector('{target_doc['selector']}');
                    if(el) el.dispatchEvent(new MouseEvent('click', {{ view: window, bubbles: true, cancelable: true }}));
                }})()
                """
                await self.agent.evaluate(click_js)
                await asyncio.sleep(1.5)
                
                # Check for intercepted URLs
                captured = await self.agent.evaluate("(() => { return window.__capturedUrls.length > 0 ? window.__capturedUrls[0] : null; })()")
                if captured:
                    logging.info(f"🎯 Interceptor caught popup URL: {captured}")
                    target_url = captured
                else:
                    # Check for in-page modal
                    modal_popped = await self.agent.evaluate("(() => { return document.querySelectorAll('[role=\"dialog\"], .modal, .popup, .el-dialog, .ant-modal, .arco-modal').length > 0; })()")
                    if not modal_popped:
                        logging.warning("⚠️ AI Referee: No modal found. Synthetic Event likely ignored by React virtual wall!")
                        logging.info("💣 Tier 2: Degrading to physical CDP click (isTrusted=true)...")
                        await self.agent.click(target_doc['selector'], mode="smart")
                        await asyncio.sleep(2)
            
            # 4. Handle Result (Navigate or Read Modal)
            if target_url:
                logging.info(f"🚀 Bypassing popup blocker, navigating to {target_url} directly...")
                current_url = await self.agent.evaluate("window.location.href")
                await self.agent.navigate(target_url)
                await asyncio.sleep(5)
                
                logging.info("📖 Extracting external document content...")
                doc_text = await self.agent.evaluate("document.body.innerText.substring(0, 1500).replace(/\\n/g, ' ')")
                self.learned_rules = f"RULES EXTRACTED FROM [{target_doc['text']}]: \n{doc_text}"
                logging.info("🔙 Finished reading. Navigating back to workspace...")
                await self.agent.navigate(current_url)
                await asyncio.sleep(3)
                
            else:
                logging.info("📖 Reading in-page modal content...")
                read_js = """
                (() => {
                    const modals = Array.from(document.querySelectorAll('[role="dialog"], .modal, .popup, .el-dialog, .ant-modal, .arco-modal'));
                    if (modals.length > 0) {
                        let best = modals.sort((a,b) => b.innerText.length - a.innerText.length)[0];
                        return "MODAL CONTENT: " + best.innerText.substring(0, 1500).replace(/\\n/g, ' ');
                    }
                    return document.body.innerText.substring(0, 1000).replace(/\\n/g, ' ');
                })()
                """
                tutorial_text = await self.agent.evaluate(read_js)
                self.learned_rules = f"RULES EXTRACTED FROM [{target_doc['text']}]: \n{tutorial_text}"
                
                logging.info("🧹 Closing tutorial modal...")
                close_js = """
                (() => {
                    const closeBtns = Array.from(document.querySelectorAll('button, a, i, span, svg'));
                    for (let btn of closeBtns) {
                        const t = (btn.innerText || btn.className || btn.getAttribute('aria-label') || '').toLowerCase();
                        if (t.includes('close') || t.includes('关闭') || t === 'x' || t.includes('icon-close')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                })()
                """
                closed = await self.agent.evaluate(close_js)
                if closed:
                    logging.info("✅ Tutorial modal closed.")
                else:
                    logging.warning("⚠️ Could not find close button.")
                await asyncio.sleep(1)
            
        else:
            logging.warning("⚠️ No explicit tutorial links found. Degrading to page scanning...")
            page_text = await self.agent.evaluate("document.body ? document.body.innerText.substring(0, 500).replace(/\\n/g, ' ') : ''")
            if page_text:
                self.learned_rules = f"BASIC LAYOUT CONTEXT: {page_text.strip()}"
            else:
                self.learned_rules = "No specific rules found. Proceed with default caution."
                
        logging.info(f"✅ Phase 0 Complete. Extracted Knowledge length: {len(self.learned_rules)}")


    async def verify_action_result(self, action_intent: str, expected_state: str, fallback_selector: str = None) -> bool:
        logging.info("====================================")
        logging.info(f"🧐 [Verification System] Running Completion Detection...")
        logging.info(f"   Intent: {action_intent}")
        logging.info(f"   Expected: {expected_state}")
        
        if self.use_llm and self.openai_api_key:
            try:
                logging.info("📸 Taking visual snapshot for AI referee...")
                snapshot = await self.agent.visual_snapshot(limit=40)
                items = snapshot.get("items", [])
                snapshot_text = json.dumps([{"role": i.get("role"), "text": i.get("text"), "tag": i.get("tag")} for i in items], ensure_ascii=False)
                
                import openai
                client = openai.AsyncOpenAI(api_key=self.openai_api_key)
                
                prompt = (
                    f"You are a strict QA referee for a browser automation agent.\n"
                    f"The agent just attempted the following action: '{action_intent}'\n"
                    f"We expect the state to be: '{expected_state}'\n\n"
                    f"CRITICAL RULES TO ENFORCE:\n{self.learned_rules}\n\n"
                    f"Here is a semantic snapshot of the current visible page elements:\n"
                    f"{snapshot_text[:2000]}\n\n"
                    f"Does the snapshot confirm the expected state was achieved and rules were followed?\n"
                    f"Reply exactly 'SUCCESS' if achieved, or 'FAILED: <reason>' if not."
                )
                
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=50,
                    temperature=0
                )
                
                decision = response.choices[0].message.content.strip()
                logging.info(f"🤖 AI Referee Decision: {decision}")
                
                if decision.startswith("SUCCESS"):
                    return True
                else:
                    logging.warning("AI Verification failed!")
                    return False
            except Exception as e:
                logging.warning(f"AI Verification error: {e}. Degrading to Option 1.")
                
        fallback_target = fallback_selector or expected_state
        return await self.agent.verify_dom_state(fallback_target, timeout=3)


    async def execute_with_verification(self, action_func, action_intent: str, expected_state: str, fallback_selector: str = None, retries: int = 2):
        for attempt in range(1, retries + 1):
            logging.info(f"\n🚀 Executing Action Attempt {attempt}/{retries}: {action_intent}")
            await action_func()
            await asyncio.sleep(2)
            
            success = await self.verify_action_result(action_intent, expected_state, fallback_selector)
            
            if success:
                logging.info("✅ Action verified successfully!")
                return True
                
            logging.warning(f"❌ Action verification failed on attempt {attempt}. Retrying...")
            await asyncio.sleep(2)
            
        raise ActionFailedError(f"Action failed after {retries} attempts: {action_intent}")

    async def run_sample_mission(self, url: str):
        await self.initialize("Cognitive Agent Phase 0 Demo")
        try:
            await self.execute_with_verification(
                action_func=lambda: self.agent.navigate(url),
                action_intent=f"Navigate to {url}",
                expected_state="Page loaded",
                fallback_selector="body"
            )
            
            await self.pre_flight_learning()
            
            logging.info("Proceeding with task using learned rules...")
            try:
                await self.execute_with_verification(
                    action_func=lambda: self.agent.click("button.fake-btn"),
                    action_intent="Click primary button",
                    expected_state="Popup open",
                    fallback_selector=".popup",
                    retries=1
                )
            except ActionFailedError:
                logging.info("🎉 CDS Caught Failure!")
        finally:
            await self.agent.close()

if __name__ == "__main__":
    logging.info("Starting Cognitive Executor Demo with Phase 0 Learning...")
    loop = CognitiveAgentLoop(use_llm=True)
    asyncio.run(loop.run_sample_mission("https://uplog.cc/card"))
