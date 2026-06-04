import asyncio
import sys
import os
import urllib.parse
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

sys.stdout.reconfigure(encoding='utf-8')

# High-traffic digital product/efficiency template keywords
KEYWORDS = ["Notion模板", "Excel模板", "自律计划表"]
RESULTS_FILE = r"C:\Users\86159\.gemini\antigravity\brain\3661c0cb-c572-43e2-aea9-14ff26f1c6ea\scratch\results.json"

async def scrape_keyword(agent, query):
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.xiaohongshu.com/search_result?keyword={encoded_query}"
    
    print(f"\n🚀 [Scraper] Navigating to: {search_url}")
    await agent.navigate(search_url)
    
    # Wait for page to load and first batch of cards to render
    print("Waiting 6 seconds for initial cards to render...")
    await asyncio.sleep(6)
    
    # Scroll down to trigger lazy loading of more viral cards
    print("Scrolling down to fetch more notes...")
    scroll_js = "window.scrollBy({ top: 1000, behavior: 'smooth' });"
    await agent.evaluate(scroll_js)
    await asyncio.sleep(4)
    
    # Extract DOM data using corrected JS (push instead of append)
    extract_js = """
        (() => {
            const cards = Array.from(document.querySelectorAll("section.note-item, div.note-item, div.feeds-container article"));
            const data = [];
            
            cards.forEach(card => {
                const titleEl = card.querySelector(".title, .note-title, a.title, .title-text, .desc");
                const authorEl = card.querySelector(".author, .name, .nickname");
                const likesEl = card.querySelector(".like, .like-num, .count");
                const linkEl = card.querySelector("a");
                
                if (titleEl) {
                    data.push({
                        title: titleEl.innerText.trim(),
                        author: authorEl ? authorEl.innerText.trim() : "未知作者",
                        likes: likesEl ? likesEl.innerText.trim() : "0",
                        link: linkEl ? linkEl.href : ""
                    });
                }
            });
            
            // Fallback if structured selectors failed
            if (data.length === 0) {
                const fallbackTitles = Array.from(document.querySelectorAll("span.title, div.title, .note-title, .title-text, a.title"));
                fallbackTitles.forEach(el => {
                    data.push({
                        title: el.innerText.trim(),
                        author: "未知",
                        likes: "未知",
                        link: ""
                    });
                });
            }
            
            return data;
        })()
    """
    
    notes = await agent.evaluate(extract_js)
    
    # Data cleaning and de-duplication
    cleaned = []
    seen = set()
    if notes and isinstance(notes, list):
        for n in notes:
            title = n.get("title", "").strip()
            if not title:
                continue
            # Skip any rental house leaks
            if "租房" in title or "房东" in title:
                continue
            if title not in seen:
                seen.add(title)
                cleaned.append(n)
    
    print(f"Successfully scraped {len(cleaned)} notes for word '{query}'.")
    return cleaned

async def main():
    print("=" * 80)
    print("📈 Xiaohongshu Viral Topic Scraper (No-Face Efficiency Templates Track)")
    print("=" * 80)
    
    agent = BrowserAgent("ws://localhost:8765/client")
    all_data = {}
    
    try:
        await agent.connect()
        await agent.init("小红书爆款资料与效率模板调研")
        
        for kw in KEYWORDS:
            try:
                notes = await scrape_keyword(agent, kw)
                all_data[kw] = notes
            except Exception as kw_err:
                print(f"Error scraping '{kw}': {kw_err}")
                all_data[kw] = []
                
        # Write results to scratch json file
        os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=4)
        print(f"\n✅ All scraped data successfully exported to: {RESULTS_FILE}")
        
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
    finally:
        await agent.close()
        print("\n" + "=" * 80)
        print("🏁 Scraper process finished!")
        print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())
