import asyncio
import sys
import os
import json
import urllib.parse

# Ensure SDK path is available
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from agent_core import BrowserAgent

sys.stdout.reconfigure(encoding='utf-8')

KEYWORD = "Notion模板"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "comments_output.json")

async def scrape_all_comments_for_first_note():
    agent = BrowserAgent("ws://localhost:8765/client")
    
    try:
        # 1. 连接服务并启动标签页
        await agent.connect()
        await agent.init("小红书全量评论抓取")
        
        encoded_query = urllib.parse.quote(KEYWORD)
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={encoded_query}"
        
        print(f"🚀 [Scraper] 导航到搜索页面: {search_url}")
        await agent.navigate(search_url)
        await asyncio.sleep(6)
        
        # 2. 点击首张卡片的图片以打开详情 Modal 弹窗
        card_selector = "section.note-item:nth-of-type(1) img, div.note-item:nth-of-type(1) img, .feeds-container article:nth-of-type(1) img"
        print(f"点击首张卡片图片: {card_selector}")
        try:
            await agent.click(card_selector)
        except Exception as click_err:
            print(f"点击失败，尝试使用 JS 强制点击卡片图片...")
            click_fallback_js = """
                (() => {
                    const card = document.querySelector("section.note-item img, div.note-item img, div.feeds-container article img, a.title");
                    if (card) {
                        card.click();
                        return true;
                    }
                    return false;
                })()
            """
            await agent.evaluate(click_fallback_js)
            
        print("等待弹窗加载...")
        await asyncio.sleep(6)
        
        # 3. 循环滚动并自动点击展开更多按钮
        prev_count = 0
        no_grow_count = 0
        max_scrolls = 35
        safety_limit = 100  # 安全上限，避免热门笔记评论过多导致无限卡顿
        
        print("\n⏳ 开始进入深度评论加载循环...")
        for i in range(max_scrolls):
            # 1. 向上微调滚动，派发 scroll 事件（利用 CDP 发起两次独立请求，彻底解决后台浏览器标签页 setTimeout 降频限制）
            await agent.evaluate("""
                (() => {
                    const getScroller = () => {
                        const noteScroller = document.querySelector(".note-scroller");
                        if (noteScroller) return noteScroller;
                        const modal = document.querySelector(".note-detail-mask, .note-container, .modal-container");
                        if (modal) {
                            const divs = Array.from(modal.querySelectorAll("div"));
                            for (let div of divs) {
                                const style = window.getComputedStyle(div);
                                if (div.scrollHeight > div.clientHeight && (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                                    return div;
                                }
                            }
                        }
                        return window;
                    };
                    const scroller = getScroller();
                    if (scroller === window) {
                        window.scrollBy(0, -150);
                        window.dispatchEvent(new Event('scroll', { bubbles: true }));
                    } else {
                        scroller.scrollTop -= 150;
                        scroller.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }
                })()
            """)
            
            # 2. 在 Python 端休眠 150ms，彻底释放浏览器 JS 帧
            await asyncio.sleep(0.15)
            
            # 3. 向下大幅度滚动，展开回复，检查触底并返回状态
            scroll_res = await agent.evaluate("""
                (() => {
                    const getScroller = () => {
                        const noteScroller = document.querySelector(".note-scroller");
                        if (noteScroller) return noteScroller;
                        const modal = document.querySelector(".note-detail-mask, .note-container, .modal-container");
                        if (modal) {
                            const divs = Array.from(modal.querySelectorAll("div"));
                            for (let div of divs) {
                                const style = window.getComputedStyle(div);
                                if (div.scrollHeight > div.clientHeight && (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                                    return div;
                                }
                            }
                        }
                        return window;
                    };
                    
                    const scroller = getScroller();
                    if (scroller === window) {
                        window.scrollBy(0, 1200);
                        window.dispatchEvent(new Event('scroll', { bubbles: true }));
                    } else {
                        scroller.scrollTop += 1200;
                        scroller.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }
                    
                    // 点击折叠的“展开 x 条回复”或“查看更多评论”
                    let clicked = 0;
                    const expandButtons = Array.from(document.querySelectorAll(".show-more, .expand-btn, [class*='expand'], [class*='more']"))
                        .concat(Array.from(document.querySelectorAll("div, span, p"))
                        .filter(el => el.innerText && (el.innerText.includes("展开") || el.innerText.includes("更多回复"))));
                        
                    expandButtons.forEach(btn => {
                        if (btn.innerText && btn.innerText.length < 25 && btn.offsetHeight > 0) {
                            try {
                                btn.click();
                                clicked++;
                            } catch(e) {}
                        }
                    });
                    
                    // 计算当前 DOM 中已渲染且去重后的评论条数
                    const seen = new Set();
                    const items = document.querySelectorAll(".comment-inner-container, .comment-item-layout, .comment-item");
                    items.forEach(item => {
                        const authorEl = item.querySelector(".author, .nickname, .name, .user-name");
                        const contentEl = item.querySelector(".content, .comment-content, .text, .content-text");
                        if (contentEl) {
                            const author = authorEl ? authorEl.innerText.trim() : "匿名用户";
                            const content = contentEl.innerText.trim();
                            seen.add(`${author}||${content}`);
                        }
                    });
                    
                    // 检测小红书特有的底部 "- THE END -" 或“没有更多评论”标识
                    const reachedEnd = Array.from(document.querySelectorAll("div, span, p, .end-container, .end-text"))
                        .some(el => {
                            if (!el.innerText) return false;
                            const txt = el.innerText.toUpperCase();
                            return txt.includes("- THE END -") || txt.includes("已经到底") || txt.includes("没有更多评论");
                        });
                    
                    return {
                        clicked: clicked,
                        commentsCount: seen.size,
                        reachedBottom: reachedEnd,
                        scrollTop: scroller === window ? document.documentElement.scrollTop : scroller.scrollTop,
                        scrollHeight: scroller === window ? document.documentElement.scrollHeight : scroller.scrollHeight,
                        tagName: scroller === window ? "WINDOW" : scroller.tagName,
                        className: scroller === window ? "" : scroller.className
                    };
                })()
            """)
            
            comments_count = scroll_res.get("commentsCount", 0)
            clicked_buttons = scroll_res.get("clicked", 0)
            reached_bottom = scroll_res.get("reachedBottom", False)
            s_top = scroll_res.get("scrollTop", 0)
            s_height = scroll_res.get("scrollHeight", 0)
            tag = scroll_res.get("tagName", "")
            cls = scroll_res.get("className", "")
            
            print(f"   [第 {i+1} 次滚动] 滚动容器: <{tag} class='{cls}'>, scrollTop: {s_top}, scrollHeight: {s_height}, 去重评论数: {comments_count} 条 (本次自动展开回复 {clicked_buttons} 处)")
            
            if reached_bottom:
                print("🎉 检测到页面底部的触底标识（如 '- THE END -'），提前结束滚动，成功收尾！")
                break
                
            if comments_count >= safety_limit:
                print(f"已达到预设的安全抓取上限 ({safety_limit} 条评论)，停止加载。")
                break
                
            if comments_count == prev_count:
                no_grow_count += 1
                if no_grow_count >= 8:
                    print("检测到评论数已不再增长，已成功触底。")
                    break
            else:
                no_grow_count = 0
                
            prev_count = comments_count
            await asyncio.sleep(3)  # 等待新内容网络加载以及DOM渲染
            
        # 4. 一次性获取所有已加载的评论详情
        print("\n提取完整评论详情数据...")
        extract_js = """
            (() => {
                const container = document.querySelector(".note-detail-mask, .note-container, .modal-container") || document.body;
                
                const titleEl = container.querySelector(".title, .note-title, h1.title, .desc-title, h1");
                const descEl = container.querySelector(".desc, .desc-content, .note-text, #detail-desc, .desc-text");
                
                const titleText = titleEl ? titleEl.innerText.trim() : "";
                const descText = descEl ? descEl.innerText.trim() : "";
                
                const comments = [];
                const commentItems = container.querySelectorAll(".comment-inner-container");
                const itemsToProcess = commentItems.length > 0 ? commentItems : container.querySelectorAll(".comment-item-layout, .comment-item");
                
                const seen = new Set();
                itemsToProcess.forEach((item) => {
                    const authorEl = item.querySelector(".author, .nickname, .name, .user-name");
                    const contentEl = item.querySelector(".content, .comment-content, .text, .content-text");
                    const likeEl = item.querySelector(".like-count, .likes, [class*='like']");
                    const isPinned = !!item.querySelector(".pinned, .pin-tag, .pinned-comment, [class*='pin']");
                    
                    if (contentEl) {
                        const author = authorEl ? authorEl.innerText.trim() : "匿名用户";
                        const content = contentEl.innerText.trim();
                        const key = `${author}||${content}`;
                        
                        if (!seen.has(key)) {
                            seen.add(key);
                            comments.push({
                                index: comments.length + 1,
                                author: author,
                                content: content,
                                likes: likeEl ? likeEl.innerText.trim() : "0",
                                pinned: isPinned
                            });
                        }
                    }
                });
                
                return {
                    title: titleText || document.title,
                    description: descText,
                    total_comments_scraped: comments.length,
                    comments: comments
                };
            })()
        """
        
        final_data = await agent.evaluate(extract_js)
        
        # 5. 关闭 Modal
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
        
        # 写入 JSON 文件
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=4)
            
        print(f"\n🎉 抓取成功！")
        print(f"   笔记标题: {final_data['title']}")
        print(f"   总共成功捕获并解析了 {final_data['total_comments_scraped']} 条评论数据（已包含展开的二级回复）。")
        print(f"   数据已保存至: {OUTPUT_FILE}")
        
    except Exception as e:
        print(f"❌ 运行过程中出错: {e}")
    finally:
        await agent.close()

if __name__ == "__main__":
    asyncio.run(scrape_all_comments_for_first_note())
