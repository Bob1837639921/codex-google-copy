import asyncio
import sys
import os
import json
import urllib.parse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

sys.stdout.reconfigure(encoding='utf-8')

KEYWORDS = ["Notion模板", "Excel模板", "自律计划表"]
DETAILS_FILE = r"C:\Users\86159\.gemini\antigravity\brain\3661c0cb-c572-43e2-aea9-14ff26f1c6ea\scratch\details.json"

async def scrape_detail_via_click(agent, keyword):
    encoded_query = urllib.parse.quote(keyword)
    search_url = f"https://www.xiaohongshu.com/search_result?keyword={encoded_query}"
    
    print(f"\n🚀 [Click Scraper] Navigating to search result: {search_url}")
    await agent.navigate(search_url)
    await asyncio.sleep(6)
    
    # 1. Click the first note card to open detail overlay
    # Select the first section.note-item, a.title, or div.note-item
    card_selector = "section.note-item:nth-of-type(1), div.note-item:nth-of-type(1), .feeds-container article:nth-of-type(1)"
    print(f"Clicking the first note card under '{keyword}' to open detail overlay...")
    try:
        await agent.click(card_selector)
    except Exception as click_err:
        print(f"Failed to click card selector: {click_err}. Trying fallback card selector...")
        # Fallback click via JS
        click_fallback_js = """
            (() => {
                const card = document.querySelector("section.note-item, div.note-item, div.feeds-container article, a.title");
                if (card) {
                    card.click();
                    return true;
                }
                return false;
            })()
        """
        clicked = await agent.evaluate(click_fallback_js)
        print(f"Fallback click result: {clicked}")
        
    await asyncio.sleep(6) # Wait for detail modal to pop up and load comments
    
    # 2. Extract content from overlay via evaluate JS
    extract_overlay_js = """
        (() => {
            // Find overlay container
            const container = document.querySelector(".note-container, .modal-container, .note-detail-mask, .interaction-container") || document.body;
            
            // Title and description
            const titleEl = container.querySelector(".title, .note-title, h1.title, .note-content h1, .desc-title");
            const descEl = container.querySelector(".desc, .desc-content, .note-text, #detail-desc, .note-content, .desc-text");
            
            const titleText = titleEl ? titleEl.innerText.trim() : "";
            const descText = descEl ? descEl.innerText.trim() : "";
            
            // Images in overlay
            const images = [];
            const imgEls = container.querySelectorAll(".media-container img, .swiper-slide img, .note-content img, .slider-container img, .image-wrapper img");
            imgEls.forEach(img => {
                if (img.src && img.src.startsWith("http") && !img.src.includes("avatar") && !images.includes(img.src)) {
                    images.push(img.src);
                }
            });
            
            // Comments in overlay
            const comments = [];
            const commentItems = container.querySelectorAll(".comment-item, .comment-inner-container, .comment-item-container, .comment-item-layout");
            commentItems.forEach(item => {
                const authorEl = item.querySelector(".author, .nickname, .name");
                const contentEl = item.querySelector(".content, .comment-content, .text, .content-text");
                const isPinned = !!item.querySelector(".pinned, .pin-tag, .pinned-comment, [class*='pin']");
                
                if (contentEl) {
                    comments.push({
                        author: authorEl ? authorEl.innerText.trim() : "未知",
                        content: contentEl.innerText.trim(),
                        pinned: isPinned
                    });
                }
            });
            
            // If overlay selectors failed to find comments, extract raw comment texts
            if (comments.length === 0) {
                const textBlocks = Array.from(container.querySelectorAll("div, span, p"))
                    .map(el => (el.innerText || "").trim())
                    .filter(t => t.length > 4 && t.length < 150 && !t.includes("分享") && !t.includes("点赞") && !t.includes("收藏"));
                
                // Deduplicate and filter out obvious description matches
                const uniqueTexts = Array.from(new Set(textBlocks)).slice(0, 15);
                uniqueTexts.forEach(t => {
                    comments.push({
                        author: "未知",
                        content: t,
                        pinned: false
                    });
                });
            }
            
            // Close the overlay using Escape or close-btn click (will be executed after return)
            return {
                title: titleText || document.title,
                description: descText,
                images: images.slice(0, 5),
                comments: comments.slice(0, 15)
            };
        })()
    """
    
    data = await agent.evaluate(extract_overlay_js)
    
    # Try closing the modal by simulating clicking the close button or pressing Escape
    close_js = """
        (() => {
            const closeBtn = document.querySelector(".close-box, .close-btn, .close, button.close, [class*='close-box'], [class*='close-btn']");
            if (closeBtn) {
                closeBtn.click();
                return "closed_via_btn";
            }
            // Dispatch escape key
            const event = new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true });
            document.dispatchEvent(event);
            return "closed_via_esc";
        })()
    """
    close_res = await agent.evaluate(close_js)
    print(f"Closed modal action: {close_res}")
    await asyncio.sleep(2)
    
    print(f"Scraped overlay data. Title: '{data['title'][:30]}...'. Comments found: {len(data['comments'])}.")
    return data

async def main():
    print("=" * 80)
    print("🎬 Xiaohongshu Modal Overlay Click-Scraper (Bypassing Detail Wind-Control)")
    print("=" * 80)
    
    agent = BrowserAgent("ws://localhost:8765/client")
    scraped_details = {}
    
    try:
        await agent.connect()
        await agent.init("小红书详情页点击拆解")
        
        for kw in KEYWORDS:
            try:
                res = await scrape_detail_via_click(agent, kw)
                scraped_details[kw] = res
            except Exception as e:
                print(f"Error scraping detail via click for '{kw}': {e}")
                scraped_details[kw] = {
                    "title": f"Failed to scrape {kw}",
                    "description": "",
                    "images": [],
                    "comments": []
                }
                
        # Export to details JSON
        os.makedirs(os.path.dirname(DETAILS_FILE), exist_ok=True)
        with open(DETAILS_FILE, "w", encoding="utf-8") as f:
            json.dump(scraped_details, f, ensure_ascii=False, indent=4)
        print(f"\n✅ All clicked note details successfully exported to: {DETAILS_FILE}")
        
    except Exception as e:
        print(f"\n❌ Script failed: {e}")
    finally:
        await agent.close()
        print("\n" + "=" * 80)
        print("🏁 Click-Scraper finished!")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
