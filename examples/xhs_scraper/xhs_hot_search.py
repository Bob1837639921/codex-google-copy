import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    print("=" * 70)
    print("🚀 Connecting to NodeX Browser Agent to Scrape Xiaohongshu Hot Searches...")
    print("=" * 70)
    
    agent = BrowserAgent("ws://localhost:8765/client")
    try:
        await agent.connect()
        await agent.init("小红书全网热搜词调研")
        
        # 1. Navigate to Xiaohongshu Homepage
        print("\n[Step 1] Navigating Chrome to Xiaohongshu Homepage...")
        await agent.navigate("https://www.xiaohongshu.com")
        print("Waiting 5 seconds for page load...")
        await asyncio.sleep(5)
        
        # 2. Check if search input exists and click it to open hot search dropdown
        print("\n[Step 2] Locating search input and focusing it...")
        snapshot = await agent.snapshot()
        
        search_selector = "input.search-input, input[placeholder*='搜索'], #search-input"
        print(f"Clicking search input to trigger dropdown: {search_selector}")
        await agent.click(search_selector)
        await asyncio.sleep(3)
        
        # 3. Take a snapshot of the dropdown area or evaluate DOM to get hot searches
        print("\n[Step 3] Extracting hot search terms from dropdown...")
        
        # Evaluation script targeting:
        # - '.trending-item' (usual hot search item class)
        # - '.history-item'
        # - Any dropdown list elements under '.search-input' popover
        # - Or just generic keywords from dropdown divs
        extract_hot_js = """
            (() => {
                // Select hot items or search suggestion items
                const elements = Array.from(document.querySelectorAll("div.trending-item, div.search-trending-item, .trending-text, a.trending-item, div.popover-container div, div.search-input-container div"));
                
                // Let's also look for text content that starts with numbers (like 1, 2, 3...) which represent rank
                const hotWords = [];
                const allTexts = Array.from(document.querySelectorAll("div, span, p, a")).map(el => (el.innerText || "").trim());
                
                // Inspect typical popover class or text keywords
                const popover = document.querySelector(".search-input-box") || document.querySelector(".popover") || document.body;
                const popoverTexts = Array.from(popover.querySelectorAll("div, span, a, p")).map(el => (el.innerText || "").trim());
                
                // Filter unique, non-empty short phrases in popover area
                const seen = new Set();
                const filtered = popoverTexts.filter(t => {
                    if (t.length > 1 && t.length < 25 && !seen.has(t)) {
                        seen.add(t);
                        return true;
                    }
                    return false;
                });
                
                return filtered;
            })()
        """
        
        popover_items = await agent.evaluate(extract_hot_js)
        
        print("\n=== Real-time Scraped Xiaohongshu Search Popover Elements ===")
        if popover_items and isinstance(popover_items, list):
            count = 0
            for item in popover_items:
                # Filter out generic UI text and keep potential hot searches
                clean_item = item.replace("\n", " ")
                if not any(k in clean_item for k in ["搜索", "取消", "历史", "清除", "删除", "关闭"]):
                    count += 1
                    print(f"  🔥 Hot Search/Suggest #{count}: {clean_item}")
                    if count >= 15:
                        break
        else:
            print("  No popover elements returned. Let's try direct search suggestions via API or generic scraping.")
            
        # 4. Fallback: Search for trending tags or hot topics page on Xiaohongshu
        # Let's navigate to Xiaohongshu creator dashboard hot topic hub if needed, 
        # or list top notes on the landing feed that have high likes.
        print("\n[Step 4] Extracting high-liked notes from home feed as fallback...")
        feed_extract_js = """
            (() => {
                const notes = Array.from(document.querySelectorAll("section.note-item, div.note-item"));
                const data = [];
                notes.forEach(note => {
                    const title = note.querySelector(".title, .note-title");
                    const likes = note.querySelector(".like, .like-num, .count");
                    if (title) {
                        data.push({
                            title: title.innerText.trim(),
                            likes: likes ? likes.innerText.trim() : "0"
                        });
                    }
                });
                return data;
            })()
        """
        feed_notes = await agent.evaluate(feed_extract_js)
        if feed_notes:
            print("\n=== Top Trending Home Feed Notes ===")
            for idx, fn in enumerate(feed_notes[:10], 1):
                print(f"  ⭐ Feed Note #{idx}: {fn['title']} (Likes/Interactions: {fn['likes']})")
                
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
    finally:
        await agent.close()
        print("\n" + "=" * 70)
        print("🏁 Xiaohongshu Hot Search Scraper complete!")
        print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
