import asyncio
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

sys.stdout.reconfigure(encoding='utf-8')

# 3 top-tier viral notes to scrape
NOTES_TO_SCRAPE = [
    {
        "type": "Notion",
        "url": "https://www.xiaohongshu.com/explore/669b30a3000000000a0047a3",
        "title_hint": "玩转Notion一通百通"
    },
    {
        "type": "Excel",
        "url": "https://www.xiaohongshu.com/explore/6840fdae000000001101e415",
        "title_hint": "老板喜欢的出纳日记账"
    },
    {
        "type": "自律",
        "url": "https://www.xiaohongshu.com/explore/6648b5e300000000050062c4",
        "title_hint": "你敢坚持一个月吗"
    }
]

DETAILS_FILE = r"C:\Users\86159\.gemini\antigravity\brain\3661c0cb-c572-43e2-aea9-14ff26f1c6ea\scratch\details.json"

async def scrape_detail(agent, note_info):
    url = note_info["url"]
    print(f"\n🚀 [Detail Scraper] Navigating to: {url} ({note_info['type']})")
    await agent.navigate(url)
    
    # Wait for the note layout and comments to render
    print("Waiting 6 seconds for page elements and comments to fully load...")
    await asyncio.sleep(6)
    
    # Run evaluation script on active page
    extract_details_js = """
        (() => {
            // 1. Get note title and description
            const titleEl = document.querySelector(".title, .note-title, h1.title, .note-content h1");
            const descEl = document.querySelector(".desc, .desc-content, .note-text, #detail-desc, .note-content");
            
            const titleText = titleEl ? titleEl.innerText.trim() : "";
            const descText = descEl ? descEl.innerText.trim() : "";
            
            // 2. Get images
            const images = [];
            const imgEls = document.querySelectorAll(".media-container img, .swiper-slide img, .note-content img, .slider-container img");
            imgEls.forEach(img => {
                if (img.src && img.src.startsWith("http") && !img.src.includes("avatar") && !images.includes(img.src)) {
                    images.push(img.src);
                }
            });
            
            // 3. Get comments
            const comments = [];
            const commentItems = document.querySelectorAll(".comment-item, .comment-inner-container, .comment-item-container");
            commentItems.forEach(item => {
                const authorEl = item.querySelector(".author, .nickname, .name");
                const contentEl = item.querySelector(".content, .comment-content, .text");
                const isPinned = !!item.querySelector(".pinned, .pin-tag, .pinned-comment, [class*='pin']");
                
                if (contentEl) {
                    comments.push({
                        author: authorEl ? authorEl.innerText.trim() : "未知",
                        content: contentEl.innerText.trim(),
                        pinned: isPinned
                    });
                }
            });
            
            // Fallback for comments if selector failed
            if (comments.length === 0) {
                const fallbackComments = Array.from(document.querySelectorAll("[class*='comment']"))
                    .map(el => (el.innerText || "").trim())
                    .filter(t => t.length > 5 && t.length < 200 && !t.includes("回复") && !t.includes("分享"));
                
                fallbackComments.forEach(t => {
                    comments.push({
                        author: "未知",
                        content: t,
                        pinned: false
                    });
                });
            }
            
            return {
                title: titleText,
                description: descText,
                images: images.slice(0, 10),
                comments: comments.slice(0, 25)
            };
        })()
    """
    
    result = await agent.evaluate(extract_details_js)
    print(f"Scraped details successfully. Found {len(result['comments'])} comments, {len(result['images'])} images.")
    return result

async def main():
    print("=" * 80)
    print("🔬 Xiaohongshu Note Detail Scraper - Deep Retention Analysis")
    print("=" * 80)
    
    agent = BrowserAgent("ws://localhost:8765/client")
    scraped_details = {}
    
    try:
        await agent.connect()
        await agent.init("小红书爆款内页深度拆解")
        
        for note in NOTES_TO_SCRAPE:
            try:
                res = await scrape_detail(agent, note)
                scraped_details[note["type"]] = res
            except Exception as e:
                print(f"Error scraping details for {note['type']}: {e}")
                scraped_details[note["type"]] = {}
                
        # Export to details JSON
        os.makedirs(os.path.dirname(DETAILS_FILE), exist_ok=True)
        with open(DETAILS_FILE, "w", encoding="utf-8") as f:
            json.dump(scraped_details, f, ensure_ascii=False, indent=4)
        print(f"\n✅ Note detail analysis exported to: {DETAILS_FILE}")
        
    except Exception as e:
        print(f"\n❌ Execution failure: {e}")
    finally:
        await agent.close()
        print("\n" + "=" * 80)
        print("🏁 Detail scraper complete!")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
