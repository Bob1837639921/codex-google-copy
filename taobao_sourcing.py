import asyncio
import json
import os
import re
import sys
import logging

# Reconfigure stdout to UTF-8 to prevent console crash on Windows
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ensure workspace folder is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from agent_core import BrowserAgent

def parse_weight_g(text):
    """
    Parses weight string from product text and returns weight in grams (g).
    Returns None if no weight pattern matches.
    """
    # 1. Multi-pack pattern: e.g. 40g*10包, 40g * 10, 40gX10, 1.5kg*2
    multipack_match = re.search(r'(\d+(?:\.\d+)?)\s*(g|克|千克|kg|斤|公斤)?\s*[\*xX\u00d7]\s*(\d+)', text, re.IGNORECASE)
    if multipack_match:
        unit = float(multipack_match.group(1))
        unit_label = multipack_match.group(2) or "g" # default to grams if not specified
        count = int(multipack_match.group(3))
        unit_label = unit_label.lower()
        if unit_label in ('kg', '千克', '公斤'):
            unit *= 1000
        elif unit_label == '斤':
            unit *= 500
        return unit * count
        
    # 2. kg / 千克 / 公斤
    kg_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:kg|千克|公斤)', text, re.IGNORECASE)
    if kg_match:
        return float(kg_match.group(1)) * 1000
        
    # 3. jin / 斤
    jin_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:斤)', text)
    if jin_match:
        return float(jin_match.group(1)) * 500
        
    # 4. g / 克
    g_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|克)', text, re.IGNORECASE)
    if g_match:
        return float(g_match.group(1))
        
    return None

def parse_sales(sales_str):
    """
    Converts sales description (e.g. "4万+人付款", "93人付款") to numeric integer.
    """
    if not sales_str:
        return 0
    # Clean string
    s = sales_str.replace('人付款', '').replace('人收货', '').replace('人看过', '').strip()
    if '万+' in s:
        val = float(s.replace('万+', ''))
        return int(val * 10000)
    elif '万' in s:
        val = float(s.replace('万', ''))
        return int(val * 10000)
    elif '+' in s:
        val = float(s.replace('+', ''))
        return int(val)
    try:
        return int(s)
    except ValueError:
        return 0

async def main():
    agent = BrowserAgent("ws://localhost:8765/client")
    await agent.connect()
    
    # 1. Connect to or create tab group
    await agent.init("Taobao Search Research")
    await asyncio.sleep(1)
    
    # 2. Check current page or navigate to Taobao search
    # We evaluate page URL
    current_url = await agent.evaluate("window.location.href")
    if not current_url or "s.taobao.com/search" not in current_url:
        print("[淘宝搜寻] 正在导航到淘宝猫粮搜索页面...")
        await agent.navigate("https://s.taobao.com/search?q=%E7%8C%AB%E7%B2%AE")
        print("等待 5 秒完成初始化加载...")
        await asyncio.sleep(5)
    else:
        print(f"[淘宝搜寻] 当前已在淘宝页面: {current_url}，跳过导航并直接分析。")
        
    # 3. Login block loop
    while True:
        snapshot = await agent.snapshot()
        if snapshot.get("blocked_by_login", False):
            print("\n🚨 [安全验证阻断] 检测到淘宝登录框、滑块或安全验证！")
            print("🛑 操作提示：请您现在在受控浏览器窗口中【手动完成登录/验证】。")
            print("💤 脚本将每 3 秒检测一次状态，直到验证通过...")
            await asyncio.sleep(3)
        else:
            print("🎉 [状态正常] 未检测到登录墙阻断。")
            break
            
    # 4. Scroll viewport to trigger lazy loading of more products
    print("[淘宝搜寻] 正在滚动页面加载更多商品卡片...")
    for i in range(3):
        print(f"  滚动 {i+1}/3 ...")
        await agent.evaluate("window.scrollBy(0, 900)")
        await asyncio.sleep(1.5)
        
    # 5. Extract raw cards via JavaScript
    print("[淘宝搜寻] 正在评估页面DOM并抽取商品信息...")
    js_code = """
    (() => {
      const cards = Array.from(document.querySelectorAll('div, a')).filter(el => {
        const className = el.className || "";
        return className.includes('doubleCard--') || className.includes('singleCard--') || className.includes('Card--gO3Bz6bu');
      });
      
      return cards.map(card => {
        // Find title
        const titleEl = card.querySelector('[class*="title--"]');
        const title = titleEl ? titleEl.innerText : "";
        
        // Find item ID and construct direct Taobao item URL
        const wwEl = card.querySelector('[data-item]');
        const itemId = wwEl ? wwEl.getAttribute('data-item') : "";
        
        let href = "";
        if (itemId) {
          href = "https://item.taobao.com/item.htm?id=" + itemId;
        } else {
          // Fallback to Simba click or standard link
          const aElements = Array.from(card.querySelectorAll('a'));
          if (aElements.length > 0) {
            const detailLink = aElements.find(a => 
              a.href.includes('item.htm') || 
              a.href.includes('detail.tmall.com') || 
              a.href.includes('detail.taobao.com') || 
              a.href.includes('click.simba.taobao.com') || 
              a.href.includes('s.click.taobao.com')
            );
            href = detailLink ? detailLink.href : aElements[0].href;
          } else if (card.tagName === 'A') {
            href = card.href;
          }
        }
        
        // Find price
        const priceIntEl = card.querySelector('[class*="priceInt--"]');
        const priceFloatEl = card.querySelector('[class*="priceFloat--"]');
        let price = "";
        if (priceIntEl) {
          price = priceIntEl.innerText;
          if (priceFloatEl) {
            price += priceFloatEl.innerText;
          }
        }
        
        // Find sales
        const salesEl = card.querySelector('[class*="realSales--"]');
        const sales = salesEl ? salesEl.innerText : "";
        
        // Find shop name
        const shopEl = card.querySelector('[class*="shopName--"]') || card.querySelector('[class*="shop--"]');
        const shop = shopEl ? shopEl.innerText : "";
        
        return {
          title,
          price,
          sales,
          shop,
          href,
          fullText: card.innerText
        };
      });
    })()
    """
    
    raw_products = await agent.evaluate(js_code)
    print(f"[淘宝搜寻] 抓取到原始卡片数量: {len(raw_products)}")
    
    # 6. Parse and evaluate in Python
    evaluated_products = []
    seen_titles = set()
    
    for item in raw_products:
        title = item.get("title", "").strip()
        if not title:
            continue
        # De-duplicate
        if title in seen_titles:
            continue
        seen_titles.add(title)
        
        price_str = item.get("price", "")
        sales_str = item.get("sales", "")
        shop = item.get("shop", "").replace("\n", " ").strip()
        href = item.get("href", "")
        full_text = item.get("fullText", "").replace("\n", " ")
        
        # Parse Price
        try:
            price = float(price_str)
        except ValueError:
            continue
            
        # Parse Sales
        sales_num = parse_sales(sales_str)
        
        # Parse Weight
        weight_g = parse_weight_g(title)
        if weight_g is None:
            # Fallback to check weight in full text
            weight_g = parse_weight_g(full_text)
            
        if weight_g is None or weight_g <= 0:
            # Skip items with unknown weight (e.g. customized links or unclear trial pack weights)
            continue
            
        # Calculate price per kg
        price_per_kg = (price / weight_g) * 1000
        
        evaluated_products.append({
            "title": title,
            "price": price,
            "weight_g": weight_g,
            "weight_desc": f"{weight_g/1000:.2f}kg" if weight_g >= 1000 else f"{weight_g:.0f}g",
            "price_per_kg": round(price_per_kg, 2),
            "sales_num": sales_num,
            "sales_desc": sales_str,
            "shop": shop,
            "href": href
        })
        
    print(f"[淘宝搜寻] 经过规则解析与去重后，有效商品数: {len(evaluated_products)}")
    
    # 7. Apply Filter and Sort Rules
    # We want cost-effective cat food (性价比高):
    # - Low price per kg
    # - Reasonable weight (exclude micro trial packs < 200g, but keep larger test packs)
    # - High credibility (sales count >= 100 to prevent fraud)
    filtered_products = [
        p for p in evaluated_products
        if p["weight_g"] >= 200 and p["sales_num"] >= 100
    ]
    
    # Sort primarily by price_per_kg ascending
    filtered_products.sort(key=lambda x: x["price_per_kg"])
    
    print(f"[淘宝搜寻] 经过安全性过滤 (重量>=200g, 销量>=100) 后商品数: {len(filtered_products)}")
    
    # 8. Save report
    report_data = {
        "search_term": "猫粮",
        "total_extracted": len(raw_products),
        "total_valid": len(evaluated_products),
        "total_filtered": len(filtered_products),
        "rankings": filtered_products
    }
    
    report_path = r"C:\Users\86159\.gemini\antigravity\brain\221d8fa2-3bac-4ff2-80f9-f0871aac62c2\taobao_sourcing_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"[淘宝搜寻] 完整报告已保存至: {report_path}")
    
    # 9. Navigate to the best-matching item page (if any exist)
    if filtered_products:
        best_deal = filtered_products[0]
        print(f"\n🥇 [最佳性价比推荐] 正在将受控浏览器重定向到第一名商品的详情页:")
        print(f"   商品: {best_deal['title']}")
        print(f"   价格: ¥{best_deal['price']} / 规格: {best_deal['weight_desc']}")
        print(f"   性价比: ¥{best_deal['price_per_kg']}/kg")
        print(f"   店铺: {best_deal['shop']}")
        print(f"   链接: {best_deal['href']}")
        
        if best_deal['href']:
            await agent.navigate(best_deal['href'])
            await asyncio.sleep(4)
            print("[淘宝搜寻] 浏览器重定向导航完毕。")
    else:
        print("[淘宝搜寻] 警告: 未找到符合性价比和销量过滤规则的商品。")
        
    await agent.close()

if __name__ == "__main__":
    asyncio.run(main())
