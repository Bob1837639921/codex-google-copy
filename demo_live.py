"""
Codex Live Active Demo - Pure In-Memory WebSocket Automation
============================================================
An elegant, production-ready demonstrator exhibiting zero-file IPC browser control.
Perfect for showcasing automated navigation, DOM scraping, and smart login blockades.

Execute via terminal:
    python demo_live.py
"""

import asyncio
import sys
from agent_core import BrowserAgent

# Force stdout to UTF-8 to prevent Windows console encoding crashes (GBK)
sys.stdout.reconfigure(encoding='utf-8')

async def run_live_demo():
    print("==================================================================")
    print("🚀  Starting Live In-Memory Browser Agent Demonstration")
    print("==================================================================")
    
    # Initialize the high-level Browser SDK
    agent = BrowserAgent("ws://localhost:8765")
    
    try:
        # 1. Connect to the WebSocket Bridge Server
        await agent.connect()
        
        # 2. Hook/Initialize the visual Active Tab Group
        print("\n[Step 1] Initializing browser tab under Cyan Tab Group...")
        await agent.init("AI 双语直连演示 (Active Demo)")
        await asyncio.sleep(1)
        
        # 3. Control browser to navigate to Taobao
        print("\n[Step 2] Controlling browser to navigate to Taobao homepage...")
        await agent.navigate("https://www.taobao.com")
        print("Waiting 4 seconds for page initialization and rendering...")
        await asyncio.sleep(4)
        
        # 4. Grab interactive DOM elements & perform intelligent block check
        print("\n[Step 3] Activating AI viewport snapshot & login wall detection...")
        snapshot = await agent.snapshot()
        
        is_blocked = snapshot.get("blocked_by_login", False)
        dom_elements = snapshot.get("dom", [])
        
        if is_blocked:
            print("\n🚨 [ALERT / 警报] AI Agent detected a Login Modal / Popup Blockade!")
            print("==================================================================")
            print("🔍 原因：淘宝要求安全验证，弹出了密码或扫码登录拦截层。")
            print("🛑 策略：AI 遵循安全守护规则已【自动暂停】，防止强行操作引发滑块封禁。")
            print("💡 解决：请您现在在浏览器窗口中【手动扫码登录】。")
            print("         登录成功且弹窗自动关闭后，AI 即可恢复极速交互！")
            print("==================================================================")
        else:
            print("\n🎉 [SUCCESS / 畅通无阻] No login barrier detected! Viewport accessible.")
            print(f"Scraped {len(dom_elements)} interactive page nodes:")
            for item in dom_elements[:15]:
                print(f"  👉 {item}")
            
            # 5. Emulate visual interactions if we are clear
            print("\n[Step 4] Demonstration completed! Seamless live channel is active.")
            print("Feel free to ask the AI to scroll, search, or extract details now!")
            
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        print("💡 Make sure you have started 'server_live.py' and your Chrome Extension is connected.")
        
    finally:
        # Gracefully shutdown
        await agent.close()
        print("\n==================================================================")
        print("🏁  Live In-Memory Automation Loop Finished")
        print("==================================================================")

if __name__ == "__main__":
    asyncio.run(run_live_demo())
