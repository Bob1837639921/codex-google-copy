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

async def scrape_detail_via_modal(agent, keyword):
    encoded_query = urllib.parse.quote(keyword)
    search_url = f"https://www.xiaohongshu.com/search_result?keyword={encoded_query}"
    
    print(f"\n🚀 [Modal Scraper] Navigating search results: {search_url}")
    await agent.navigate(search_url)
    await asyncio.sleep(6)
    
    # Click the first card's image with link-interception to pull up modal overlay
    click_js = """
        (() => {
            // Intercept normal navigation
            document.querySelectorAll("a").forEach(a => {
                a.addEventListener("click", e => {
                    e.preventDefault();
                }, true);
            });
            
            // Trigger click on first card's image
            const img = document.querySelector("section.note-item img, div.note-item img, .feeds-container article img");
            if (img) {
                img.click();
                return "img_clicked";
            }
            return "no_img_found";
        })()
    """
    click_res = await agent.evaluate(click_js)
    print(f"Click trigger result: {click_res}")
    
    # Wait for overlay modal to render and populate comments
    print("Waiting 7 seconds for the modal popup to load...")
    await asyncio.sleep(7)
    
    # Precise extraction of overlay content
    extract_js = """
        (() => {
            const modal = document.querySelector(".note-detail-mask, .note-container, .modal-container");
            if (!modal) {
                return {
                    error: "Modal overlay not found in DOM after click!"
                };
            }
            
            // Select title, description and comments inside the modal container
            const titleEl = modal.querySelector(".title, .note-title, h1.title, .desc-title, .desc-header, h1");
            const descEl = modal.querySelector(".desc, .desc-content, .note-text, #detail-desc, .desc-text");
            
            const titleText = titleEl ? titleEl.innerText.trim() : "";
            const descText = descEl ? descEl.innerText.trim() : "";
            
            // Get comments inside modal
            const comments = [];
            const commentItems = modal.querySelectorAll(".comment-item, .comment-inner-container, .comment-item-layout");
            commentItems.forEach((item, index) => {
                const authorEl = item.querySelector(".author, .nickname, .name, .user-name");
                const contentEl = item.querySelector(".content, .comment-content, .text, .content-text");
                const isPinned = !!item.querySelector(".pinned, .pin-tag, .pinned-comment, [class*='pin']");
                
                if (contentEl) {
                    comments.push({
                        index: index + 1,
                        author: authorEl ? authorEl.innerText.trim() : "匿名用户",
                        content: contentEl.innerText.trim(),
                        pinned: isPinned
                    });
                }
            });
            
            // Extract image sources inside modal
            const images = [];
            const imgEls = modal.querySelectorAll(".media-container img, .swiper-slide img, .note-content img, .slider-container img, .image-wrapper img");
            imgEls.forEach(img => {
                if (img.src && img.src.startsWith("http") && !img.src.includes("avatar") && !images.includes(img.src)) {
                    images.push(img.src);
                }
            });
            
            return {
                status: "success",
                title: titleText,
                description: descText,
                images: images.slice(0, 5),
                comments: comments.slice(0, 15)
            };
        })()
    """
    
    data = await agent.evaluate(extract_js)
    
    # Safe close of the active modal
    close_js = """
        (() => {
            const closeBtn = document.querySelector(".close-box, .close-btn, .close, button.close, [class*='close-box'], [class*='close-btn']");
            if (closeBtn) {
                closeBtn.click();
                return "closed_via_btn";
            }
            const event = new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true });
            document.dispatchEvent(event);
            return "closed_via_esc";
        })()
    """
    await agent.evaluate(close_js)
    await asyncio.sleep(2)
    
    if data.get("status") == "success":
        print(f"✅ Successfully scraped modal data for '{keyword}':")
        print(f"   Title: {data['title']}")
        print(f"   Comments scraped: {len(data['comments'])}")
        return data
    else:
        print(f"❌ Failed to scrape modal data for '{keyword}': {data.get('error')}")
        return {
            "title": f"Failed modal scrape '{keyword}'",
            "description": "",
            "images": [],
            "comments": []
        }

async def main():
    print("=" * 80)
    print("🎯 Xiaohongshu Pop-up Detail Scraper via Browser Agent")
    print("=" * 80)
    
    agent = BrowserAgent("ws://localhost:8765/client")
    scraped_data = {}
    
    try:
        await agent.connect()
        await agent.init("小红书弹窗数据抓取")
        
        for kw in KEYWORDS:
            try:
                res = await scrape_detail_via_modal(agent, kw)
                scraped_data[kw] = res
            except Exception as e:
                print(f"Error executing modal scrape for '{kw}': {e}")
                scraped_data[kw] = {
                    "title": f"Error scraping '{kw}'",
                    "description": "",
                    "images": [],
                    "comments": []
                }
                
        # Export final data
        os.makedirs(os.path.dirname(DETAILS_FILE), exist_ok=True)
        with open(DETAILS_FILE, "w", encoding="utf-8") as f:
            json.dump(scraped_data, f, ensure_ascii=False, indent=4)
        print(f"\n✅ Modal scraped data successfully written to: {DETAILS_FILE}")
        
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
    finally:
        await agent.close()
        print("\n" + "=" * 80)
        print("🏁 Modal Scraper task finished!")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
