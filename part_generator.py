"""
F:\\CharacterBanner\\part_generator.py
======================================================
角色多维度各部位图片（头像、三视图、道具、草图等）自动生成与同步流水线
======================================================
1. 支持单角色“专属会话窗口（Single Character, Single Conversation）”，从根本上保持特征一致性并避免不同角色交叉污染。
2. 缓存会话 URL，第二次或后续生成直接导航至该 URL 进入已有上下文会话。
3. 自动匹配 localFileSystem.ts 里的 TYPE_FOLDER，将生成的图片下载、归档重命名到对应文件夹中。
4. 手术刀式回写 characterData.ts 中的 images 数组，支持追加新部位图片，且增加时间戳避开 Vite 浏览器缓存。

作者：Antigravity Team
日期：2026-06-01
"""

import os
import sys
import re
import time
import shutil
import asyncio
import json
import uuid
import logging
import argparse
import websockets

# 配置精致优雅的日志输出
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
if sys.platform.startswith('win'):
    import codecs
    sys.stdout.reconfigure(encoding='utf-8')

# ======================================================
# 1. 全局配置选项
# ======================================================
OUTPUT_ROOT = "F:/jiaose"
REACT_PROJECT_PATH = "F:/CharacterBanner"

# 尝试从本地配置文件动态加载，实现跨电脑免配置无缝适配
CONFIG_FILE_PATH = "local_config.json"
if os.path.exists(CONFIG_FILE_PATH):
    try:
        with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            if "output_root" in config_data:
                OUTPUT_ROOT = config_data["output_root"]
            if "react_project_path" in config_data:
                REACT_PROJECT_PATH = config_data["react_project_path"]
            logging.info(f"✨ 动态载入配置：图片输出路径={OUTPUT_ROOT}, React项目路径={REACT_PROJECT_PATH}")
    except Exception as e:
        logging.warning(f"读取 local_config.json 失败: {e}")
        
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads")
WS_URL = "ws://localhost:8765/client"
SESSIONS_CACHE_FILE = "chat_sessions.json"

# 本地文件夹映射 (与 localFileSystem.ts 保持 100% 绝对一致)
TYPE_FOLDER = {
    'main': '01-主视觉',
    'portrait': '02-头像半身',
    'expression': '03-表情差分',
    'turnaround': '04-三视图角度',
    'outfit': '05-服装差分',
    'prop': '06-道具武器',
    'scene': '07-场景氛围',
    'cover': '09-封面图',
    'moodboard': '10-氛围板',
    'sketch': '11-线稿结构',
    'fullBody': '12-全身立绘',
    'modelSheet': '13-标准设定图',
    'poseSheet': '14-动作姿态',
    'expressionSheet': '15-表情包',
    'detailSheet': '16-细节特写',
    'materialPalette': '17-材质色卡',
    'outfitBreakdown': '18-服装拆分',
    'damageState': '19-破损状态'
}

TYPE_LABEL = {
    'main': '主视觉',
    'portrait': '头像半身',
    'expression': '表情差分',
    'turnaround': '三视图角度',
    'outfit': '服装差分',
    'prop': '道具武器',
    'scene': '场景氛围',
    'cover': '封面图',
    'moodboard': '氛围板',
    'sketch': '线稿结构',
    'fullBody': '全身立绘',
    'modelSheet': '标准设定图',
    'poseSheet': '动作姿态',
    'expressionSheet': '表情包',
    'detailSheet': '细节特写',
    'materialPalette': '材质色卡',
    'outfitBreakdown': '服装拆分',
    'damageState': '破损状态'
}

# ======================================================
# 2. 轻量级 BrowserAgent WebSocket 控制 SDK
# ======================================================
class BrowserAgent:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.websocket = None

    async def connect(self):
        logging.info(f"正在连接到浏览器桥接服务器: {self.ws_url}...")
        try:
            self.websocket = await websockets.connect(
                self.ws_url,
                ping_interval=None,
                ping_timeout=None,
                max_size=50 * 1024 * 1024
            )
            logging.info("WebSocket 桥接连接成功！")
            return True
        except Exception as e:
            logging.error(f"连接失败！错误: {e}")
            logging.error("请确认 `server_live.py` 正在运行，并且 Chrome 扩展处于活动状态。")
            return False

    async def _send_command(self, action: str, **kwargs):
        if not self.websocket:
            raise RuntimeError("WebSocket 未连接，请先调用 connect()")
            
        cmd_id = str(uuid.uuid4())
        payload = {"id": cmd_id, "action": action}
        payload.update(kwargs)
        
        await self.websocket.send(json.dumps(payload))
        
        async for message in self.websocket:
            try:
                data = json.loads(message)
                if data.get("id") == cmd_id:
                    if data.get("status") == "error":
                        raise RuntimeError(f"浏览器操作执行失败: {data.get('error')}")
                    return data
            except json.JSONDecodeError:
                pass

    async def init(self, task_name: str = "角色多部位图片自动流水线"):
        return await self._send_command("init", taskName=task_name)

    async def snapshot(self):
        response = await self._send_command("snapshot")
        return {
            "blocked_by_login": response.get("blockedByLogin", False),
            "dom": response.get("dom", [])
        }

    async def evaluate(self, js_code: str):
        response = await self._send_command("evaluate", code=js_code)
        return response.get("result")

    async def navigate(self, url: str):
        logging.info(f"正在控制浏览器导航至: {url}")
        return await self._send_command("navigate", url=url)

    async def click(self, selector: str):
        logging.info(f"👉 [模拟真人点击] 正在移动并点击: {selector}")
        return await self._send_command("click", selector=selector)

    async def type(self, selector: str, text: str, mode: str = "smart"):
        logging.info(f"👉 [模拟真人输入] 正在移动并输入文本 (mode={mode}): '{text[:40]}...' 到 {selector}")
        return await self._send_command("type", selector=selector, text=text, mode=mode)

    async def hover(self, selector: str):
        logging.info(f"👉 [模拟真人悬停] 正在移动并悬停至: {selector}")
        return await self._send_command("hover", selector=selector)

    async def fetch_as_file(self, url: str, dest_path: str) -> dict:
        """
        【仅适用于图片文件，< 30MB】
        扩展后台带 Cookie fetch URL → base64 → Python 直接写入 dest_path。
        完全绕过 chrome.downloads，FDM 等下载管理器无感知。
        不需要中转 Downloads 文件夹，支持写入任意本地路径。
        """
        import base64, os
        logging.info(f"fetch_as_file: {url[:60]}... → {dest_path}")
        response = await self._send_command("fetchAsBase64", url=url)
        if not response or response.get("status") != "success":
            error = response.get("error", "Unknown error") if response else "No response"
            reason = response.get("reason", "") if response else ""
            logging.error(f"fetchAsBase64 failed [{reason}]: {error}")
            return {"status": "error", "error": error, "reason": reason}
        b64_data = response.get("base64", "")
        raw_bytes = base64.b64decode(b64_data)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(raw_bytes)
        size = len(raw_bytes)
        logging.info(f"Saved {size:,} bytes → {dest_path}")
        return {"status": "success", "path": dest_path, "size": size, "mime": response.get("mime", "")}

    async def download_via_blob(self, url: str, filename: str) -> dict:
        """
        【适用于非图片文件或大文件】
        扩展 Service Worker 带 Cookie fetch URL → 生成 blob: URL → chrome.downloads 下载。
        blob: URL 不会被 FDM 等第三方下载管理器拦截，后台安全，无需窗口唤醒。
        文件保存在系统 Downloads 目录，filename 指定文件名。
        """
        logging.info(f"download_via_blob: {url[:60]}... → Downloads/{filename}")
        return await self._send_command("downloadViaBlob", url=url, filename=filename)

    async def smart_save(self, url: str, dest_path: str) -> dict:
        """
        智能路由下载方法，自动选择最优下载方式：
        - 图片文件（image/*，< 30MB）→ fetch_as_file()
        - 其他文件 / 大文件 → download_via_blob()
        """
        import os
        logging.info(f"smart_save: 尝试 fetch_as_file → {dest_path}")
        result = await self.fetch_as_file(url, dest_path)
        if result.get("status") == "success":
            return result

        reason = result.get("reason", "")
        if reason in ("unsupported_mime", "file_too_large"):
            filename = os.path.basename(dest_path)
            logging.info(f"smart_save: 回退到 download_via_blob，filename={filename}（原因：{reason}）")
            return await self.download_via_blob(url, filename)

        return result

    async def close(self):
        if self.websocket:
            await self.websocket.close()
            logging.info("WebSocket 控制连接已断开。")

# ======================================================
# 3. 聊天会话管理逻辑 (持久化)
# ======================================================
def load_sessions():
    if os.path.exists(SESSIONS_CACHE_FILE):
        try:
            with open(SESSIONS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_session(char_id, url):
    sessions = load_sessions()
    sessions[char_id] = url
    with open(SESSIONS_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(sessions, f, indent=2, ensure_ascii=False)
    logging.info(f"已缓存保存角色「{char_id}」的专属会话链接: {url}")

# ======================================================
# 4. JSON 静态数据库极速同步引擎
# ======================================================
def sync_new_image_to_json(char_id: str, img_type: str, img_label: str, img_local_path: str, prompt: str):
    """
    极速将生成的图片同步写入前端的 characterAssets.json 本地数据库，杜绝任何对 TS 源码文件的改动。
    """
    json_path = os.path.join(REACT_PROJECT_PATH, "src", "constants", "characterAssets.json")
    
    # 1. 载入或初始化 JSON 数据库
    data = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logging.warning(f"读取 characterAssets.json 失败 (可能为空或损坏)，将重新创建: {e}")
            
    # 2. 确保角色节点存在
    char_data = data.setdefault(char_id, {"image": "", "images": []})
    
    # 3. 构造相对路径（使 Vite /@fs 机制发挥作用）
    rel_path = img_local_path.replace("\\", "/")
    # 将输出根路径转换为统一的相对地址
    norm_output = OUTPUT_ROOT.replace("\\", "/").rstrip("/")
    if rel_path.startswith(norm_output):
        rel_path = rel_path[len(norm_output):].lstrip("/")
        
    # 如果路径不是以 /@fs/ 开头，根据 Vite 代理要求自动配置物理代理绝对路径
    # 这能保证无论图片是在本地哪个盘（F 盘或 C 盘），Vite 均能顺畅显示而不会跨域
    proxy_path = img_local_path.replace("\\", "/")
    full_proxy_url = f"/@fs/{proxy_path}"
    
    timestamp = int(time.time() * 1000)
    new_img = {
        "id": f"img_auto_{timestamp}",
        "type": img_type,
        "label": img_label,
        "angle": "",
        "outfit": "",
        "pose": "",
        "action": "",
        "emotion": "",
        "camera": "",
        "scene": "",
        "prompt": prompt,
        "note": "DALL-E 自动化多维度生成",
        "url": f"{full_proxy_url}?t={timestamp}"
    }
    
    # 4. 覆盖更新或追加
    existing_images = char_data.get("images", [])
    filtered_images = [img for img in existing_images if img.get("type") != img_type]
    filtered_images.append(new_img)
    
    # 5. 排序（保持 main 主视觉在首位，便于展示）
    char_data["images"] = sorted(filtered_images, key=lambda x: 0 if x.get("type") == "main" else 1)
    
    # 6. 如果是主视觉，同步更新外层的单图字段
    if img_type == "main":
        char_data["image"] = new_img["url"]
        
    # 7. 写入存盘
    try:
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logging.info(f"✨ [JSON 同步成功] 角色 [{char_id}] 的「{img_label}」资产已安全写入数据库 {json_path}！")
        return True
    except Exception as e:
        logging.error(f"❌ [JSON 同步失败] 写入文件 {json_path} 遭遇错误: {e}")
        return False

# ======================================================
# 5. 下载拦截归档引擎
# ======================================================
def wait_for_new_download(download_dir: str, existing_files: set, timeout_sec: int = 90):
    logging.info(f"等待 Chrome 下载图片完成 (监听目录: {download_dir})…")
    start_time = time.time()
    
    while time.time() - start_time < timeout_sec:
        try:
            current_files = set(os.listdir(download_dir))
        except Exception as e:
            time.sleep(1)
            continue
            
        new_files = current_files - existing_files
        
        for f in new_files:
            lower_name = f.lower()
            if lower_name.endswith(('.png', '.jpg', '.jpeg', '.webp')) and not lower_name.endswith('.crdownload'):
                # 留出安全余量让操作系统释放文件锁
                time.sleep(1.5)
                full_path = os.path.join(download_dir, f)
                if os.path.exists(full_path) and os.path.getsize(full_path) > 1024:
                    return full_path
        time.sleep(1)
        
    return None

def archive_image(downloaded_file: str, char_name: str, char_id: str, img_type: str):
    safe_char_name = re.sub(r'[\\/:*?"<>|]', '-', char_name).strip() or "未命名角色"
    sub_folder_name = TYPE_FOLDER.get(img_type, "其他")
    
    # 构造 C:/Ai/character/{角色名}/{子目录名}
    target_dir = os.path.join(OUTPUT_ROOT, safe_char_name, sub_folder_name)
    os.makedirs(target_dir, exist_ok=True)
    
    ext = downloaded_file.split('.')[-1] if '.' in downloaded_file else 'png'
    # 重新命名为 char_xxxx_portrait.png，防止名字冲突，一目了然
    target_filename = f"{char_id}_{img_type}.{ext}"
    target_path = os.path.join(target_dir, target_filename)
    
    try:
        shutil.move(downloaded_file, target_path)
        normalized_url_path = target_path.replace("\\", "/")
        logging.info(f"图片归档搬运成功！归档路径: {normalized_url_path}")
        return normalized_url_path
    except Exception as e:
        logging.warning(f"直接移动失败 (可能是跨物理卷): {e}，尝试复制备用方案...")
        try:
            shutil.copy(downloaded_file, target_path)
            os.remove(downloaded_file)
            normalized_url_path = target_path.replace("\\", "/")
            logging.info(f"通过复制+删除方式搬运成功！归档路径: {normalized_url_path}")
            return normalized_url_path
        except Exception as ex:
            logging.error(f"归档移动依然失败: {ex}")
            return None

# ======================================================
# 6. ChatGPT 交互控制逻辑
# ======================================================
async def trigger_dalle_generation(agent: BrowserAgent, prompt: str):
    logging.info(f"向 ChatGPT 输入绘制 Prompt (模拟真人): {prompt[:80]}...")
    
    # 1. 使用我们通用的 type 接口输入 prompt，带有人机滑动和输入动画！
    res = await agent.type("#prompt-textarea", prompt, mode="direct")
    if res == "textarea_not_found":
        raise RuntimeError("未能在 ChatGPT 页面中找到输入框，请确认当前标签页处于 ChatGPT 对话中！")
        
    await asyncio.sleep(1.0) # 等待使发送按钮就绪并渲染出来
    
    # 2. 找到发送按钮并为其设置临时 ID，进行真人模拟点击发送！
    js_find_send = """
    (() => {
        const sendBtn = document.querySelector('button[data-testid="send-button"]') || 
                        document.querySelector('button[aria-label="Send message"]') ||
                        document.querySelector('button.mb-1.me-1') ||
                        document.querySelector('button:has(svg[viewBox="0 0 24 24"])');
        if (!sendBtn) return "not_found";
        sendBtn.id = "tmp-send-btn";
        return "ok";
    })()
    """
    find_res = await agent.evaluate(js_find_send)
    if find_res == "ok":
        await agent.click("#tmp-send-btn")
    else:
        # 兜底直接点击 DOM
        logging.warning("找不到发送按钮，通过底层 DOM 直接触发发送...")
        await agent.evaluate("""
            (() => {
                const sendBtn = document.querySelector('button[data-testid="send-button"]') || 
                                document.querySelector('button[aria-label="Send message"]');
                if (sendBtn) sendBtn.click();
            })()
        """)
        
    logging.info("提示词已由虚拟鼠标模拟输入并触发发送，等待 DALL-E 绘图。")

async def scan_existing_web_images(agent: BrowserAgent):
    js_get = """
    (() => {
        const imgs = Array.from(document.querySelectorAll('img[src*="files.oaiusercontent.com"], img[src*="/backend-api/files"], img[src*="/backend-api/estuary/content"]'));
        const srcs = imgs.map(img => img.src);
        return Array.from(new Set(srcs));
    })()
    """
    res = await agent.evaluate(js_get)
    if isinstance(res, list):
        return res
    return []

async def poll_until_image_ready(agent: BrowserAgent, pre_existing_srcs: set, timeout_sec: int = 300):
    logging.info("开始监测 DOM 生成进度...")
    start_time = time.time()
    pre_srcs_json = json.dumps(list(pre_existing_srcs))
    
    generation_started = False
    
    while time.time() - start_time < timeout_sec:
        js_poll = f"""
        (() => {{
            const bodyText = document.body ? document.body.innerText : "";
            
            // 1. 检测 ChatGPT 官方生图额度/使用频率上限，秒级拦截
            if (bodyText.includes("You've reached your limit") || 
                bodyText.includes("reached your limit") || 
                bodyText.includes("reached the limit") ||
                bodyText.includes("Please try again") ||
                bodyText.includes("You have reached your message limit") ||
                bodyText.includes("额度已达上限") ||
                bodyText.includes("达到生图额度极限") ||
                bodyText.includes("生图额度") ||
                bodyText.includes("生图限制") ||
                bodyText.includes("使用上限")) {{
                return {{ "status": "quota_limit", "error": "ChatGPT DALL-E 生图额度/频次已达今日上限（Rate Limit / Quota Exceeded）" }};
            }}

            // 2. 检测 DALL-E 临时服务错误
            if (bodyText.includes("wasn't able to generate") || 
                bodyText.includes("encountered an error") || 
                bodyText.includes("generation tool encountered") || 
                bodyText.includes("Error generating image")) {{
                return {{ "status": "error", "error": "OpenAI DALL-E 官方绘图服务发生临时错误" }};
            }}

            // 3. 检查是否有生图指示或停止按钮，代表生图已经在运行了
            const hasStopButton = document.querySelector('button[data-testid="stop-button"]') !== null ||
                                  document.querySelector('#composer-submit-button[data-testid="stop-button"]') !== null;
            
            const hasImageLoadingState = document.querySelector('[data-testid*="image-gen-loading"]') !== null ||
                                         document.querySelector('[data-testid="image-gen-loading-state-dots"]') !== null;
            
            const latestAssistantTurn = Array.from(document.querySelectorAll('[data-message-author-role="assistant"]')).pop();
            let isThinkingCurrently = false;
            let hasSpinOrLoader = false;
            if (latestAssistantTurn) {{
                const thinkBtn = Array.from(latestAssistantTurn.querySelectorAll('button')).find(b => 
                    b.innerText.includes("Thinking") || 
                    b.innerText.includes("思考") || 
                    b.innerText.includes("Thought")
                );
                if (thinkBtn) isThinkingCurrently = true;
                
                const spin = latestAssistantTurn.querySelector('svg[class*="animate-spin"]') !== null;
                const loader = latestAssistantTurn.querySelector('.streaming-loader') !== null;
                const shimmer = latestAssistantTurn.querySelector('.loading-shimmer') !== null;
                hasSpinOrLoader = spin || loader || shimmer;
            }}
            const hasThinking = isThinkingCurrently || hasSpinOrLoader;
            
            const isGeneratingCurrently = hasStopButton || hasThinking || hasImageLoadingState;

            const preSrcs = new Set({pre_srcs_json});
            const imgs = Array.from(document.querySelectorAll('img[src*="files.oaiusercontent.com"], img[src*="/backend-api/files"], img[src*="/backend-api/estuary/content"]'));
            
            if (imgs.length === 0) {{
                return {{ "status": "waiting", "isGenerating": isGeneratingCurrently }};
            }}
            
            const newImgs = imgs.filter(img => !preSrcs.has(img.src));
            if (newImgs.length === 0) {{
                return {{ "status": "waiting", "isGenerating": isGeneratingCurrently }};
            }}
            
            const latestImg = newImgs[newImgs.length - 1];
            
            if (latestImg.complete && latestImg.naturalWidth > 0) {{
                if (isGeneratingCurrently) {{
                    return {{ "status": "generating", "isGenerating": true }};
                }}
                return {{ "status": "done", "src": latestImg.src, "isGenerating": false }};
            }}
            return {{ "status": "rendering", "isGenerating": true }};
        }})()
        """
        
        res = await agent.evaluate(js_poll)
        if isinstance(res, dict):
            status = res.get("status")
            is_generating = res.get("isGenerating", False)
            
            # 如果确认了生成已经启动（即页面处于 isGenerating 状态，或者我们已经在页面等待了超过 15 秒）
            if is_generating or (time.time() - start_time > 15):
                if not generation_started:
                    logging.info("🔥 检测到 ChatGPT 已成功启动生图流程（Thinking / Loading / StopButton 激活）")
                    generation_started = True
            
            if status == "done":
                if generation_started:
                    logging.info("检测到图片已彻底生成并渲染完毕！")
                    return res.get("src")
                else:
                    logging.warning("⚠️ 警告：检测到图片 done，但生图流程未见启动，疑似旧缓存图片，继续等待新图...")
            elif status == "quota_limit":
                logging.error(f"⚠️ [生图限额拦截] 检测到 ChatGPT 官方生图限额已满：{res.get('error')}")
                return "quota_limit"
            elif status == "error":
                logging.error(f"检测到 OpenAI 官方后台发生暂时性生成错误: {res.get('error')}")
                return "error"
            elif status == "generating" or status == "rendering" or is_generating:
                logging.info("图片生成中 / 页面排版中 / AI思考中，继续监控...")
            else:
                logging.info("正在等待 ChatGPT 绘制图片流...")
        await asyncio.sleep(3)
        
    logging.error("等待图片生成超时！")
    return None

def get_prompt_similarity(p1: str, p2: str) -> float:
    """
    计算两个 Prompt 的 Jaccard 相似度（基于英文单词）
    为了避免因为共享的 Character lock 头部导致不同部位的相似度被误判为匹配，
    如果 Prompt 包含 'current asset goal:'，我们将只对比该标记之后的具体绘图目标部分。
    """
    def clean_prompt(p: str) -> str:
        p_lower = p.lower()
        if "current asset goal:" in p_lower:
            parts = p_lower.split("current asset goal:", 1)
            return parts[1]
        if "character lock:" in p_lower:
            for delimiter in ["style:", "composition:", "background:", "constraints:"]:
                if delimiter in p_lower:
                    return p_lower.split(delimiter, 1)[1]
        return p_lower

    w1 = set(re.findall(r'\w+', clean_prompt(p1)))
    w2 = set(re.findall(r'\w+', clean_prompt(p2)))
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / len(w1 | w2)

async def scan_conversation_history(agent: BrowserAgent):
    """
    通过模拟滚动的方式，绕过 ChatGPT 消息列表虚拟化(Virtualization)限制，
    完整抓取页面中所有的 (UserPrompt -> AssistantImages) 配对。
    在 JS 层面对每一个 assistant 消息在其上方查找最近的 user 消息进行局部配对，
    彻底解决滚动过程中由于部分 Turn 被虚拟化移除导致的全局配对错位问题。
    """
    js_scroll_collect = """
    (async () => {
        let container = document.querySelector('#main') || document.querySelector('main');
        while (container && container !== document.body) {
            const style = window.getComputedStyle(container);
            if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                break;
            }
            container = container.parentElement;
        }
        if (!container || container === document.body) {
            container = document.querySelector('.overflow-y-auto') || document.body;
        }
        
        const originalScrollTop = container.scrollTop;
        const userPrompts = new Map();
        const assistantImages = new Map();
        
        // Helper to collect user turns and assistant images currently in view
        const collectTurns = () => {
            const userTurns = document.querySelectorAll('section[data-turn="user"]');
            userTurns.forEach(turn => {
                const testId = turn.getAttribute('data-testid') || "";
                const m = testId.match(/conversation-turn-(\\d+)/);
                if (m) {
                    const num = parseInt(m[1], 10);
                    const text = turn.innerText || "";
                    if (text.trim().length > 0) {
                        userPrompts.set(num, text.trim());
                    }
                }
            });
            
            const assistantTurns = document.querySelectorAll('section[data-turn="assistant"]');
            assistantTurns.forEach(turn => {
                const testId = turn.getAttribute('data-testid') || "";
                const m = testId.match(/conversation-turn-(\\d+)/);
                if (m) {
                    const num = parseInt(m[1], 10);
                    const imgs = turn.querySelectorAll('img[src*="files.oaiusercontent.com"], img[src*="/backend-api/files"], img[src*="/backend-api/estuary/content"]');
                    const imageSrcs = Array.from(imgs).map(img => img.src).filter(src => !!src);
                    if (imageSrcs.length > 0) {
                        assistantImages.set(num, imageSrcs);
                    }
                }
            });
        };
        
        // Wait for turns to render (up to 5s)
        for (let i = 0; i < 50; i++) {
            if (document.querySelectorAll('section[data-turn]').length > 0) break;
            await new Promise(r => setTimeout(r, 100));
        }
        
        // Collect initial state
        collectTurns();
        
        // 1. Smooth scroll UP to the top in steps of 200px to trigger virtualization loads
        let currentScroll = container.scrollTop;
        while (currentScroll > 0) {
            currentScroll = Math.max(0, currentScroll - 200);
            container.scrollTop = currentScroll;
            container.dispatchEvent(new Event('scroll', { bubbles: true }));
            await new Promise(r => setTimeout(r, 40));
            collectTurns();
        }
        
        // Wait at the top for additional loading
        await new Promise(r => setTimeout(r, 2000));
        collectTurns();
        
        // 2. Smooth scroll DOWN to the bottom to collect everything
        const maxScroll = container.scrollHeight - container.clientHeight;
        while (currentScroll < maxScroll) {
            currentScroll = Math.min(maxScroll, currentScroll + 200);
            container.scrollTop = currentScroll;
            container.dispatchEvent(new Event('scroll', { bubbles: true }));
            await new Promise(r => setTimeout(r, 40));
            collectTurns();
        }
        
        // Wait at the bottom
        await new Promise(r => setTimeout(r, 1000));
        collectTurns();
        
        // Restore original scroll
        container.scrollTop = originalScrollTop;
        
        // Pair prompts and images: user turn N (odd) corresponds to assistant turn N + 1 (even)
        const result = [];
        for (let [num, images] of assistantImages.entries()) {
            const prompt = userPrompts.get(num - 1);
            if (prompt) {
                images.forEach(img => {
                    result.push({ prompt: prompt, image: img });
                });
            }
        }
        return result;
    })()
    """
    try:
        logging.info("⏳ 正在运行防虚拟化滚动收集器，抓取历史对话...")
        history_pairs = await agent.evaluate(js_scroll_collect)
        if not isinstance(history_pairs, list):
            logging.warning("⚠️ 滚动历史收集器未返回有效数组，降级使用空历史列表")
            return []
        
        logging.info(f"✨ 历史对话解析完毕，共分析到 {len(history_pairs)} 个 (Prompt -> Image) 配对关系")
        return history_pairs
    except Exception as ex:
        logging.error(f"❌ 滚动收集历史失败: {ex}")
        return []

async def trigger_browser_download(agent: BrowserAgent, img_src: str):
    logging.info(f"正在通过 Fetch 同源机制为图片发起安全下载...")
    js_download = f"""
    (async () => {{
        try {{
            const res = await fetch("{img_src}");
            const blob = await res.blob();
            const blobUrl = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = "dalle_{int(time.time())}.png";
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            setTimeout(() => {{
                a.remove();
                URL.revokeObjectURL(blobUrl);
            }}, 2000);
            return "trigger_success";
        }} catch(err) {{
            return "trigger_error: " + err.message;
        }}
    }})()
    """
    return await agent.evaluate(js_download)

async def capture_current_session_url(agent: BrowserAgent, char_id: str):
    """
    轮询捕获当前的真实聊天 URL (包含 /c/xxxx)，捕获成功后存盘
    """
    for _ in range(5):
        url = await agent.evaluate("window.location.href")
        if url and "/c/" in url:
            save_session(char_id, url)
            return url
        await asyncio.sleep(2)
    return None

# ======================================================
# 7. 主执行管道 (Pipeline Core)
# ======================================================
async def generate_character_part(agent: BrowserAgent, char_id: str, char_name: str, img_type: str, prompt: str, absolute_idx: int):
    logging.info("-" * 60)
    logging.info(f"【生成启动】角色: {char_name} | 类型: {TYPE_LABEL.get(img_type, img_type)} | 绝对序号: {absolute_idx}")
    
    # 0. 智能跳过已存在资产，避免重复生成
    safe_char_name = re.sub(r'[\\/:*?"<>|]', '-', char_name).strip() or "未命名角色"
    sub_folder_name = TYPE_FOLDER.get(img_type, "其他")
    target_dir = os.path.join(OUTPUT_ROOT, safe_char_name, sub_folder_name)
    target_path = os.path.join(target_dir, f"{char_id}_{img_type}.png")
    if os.path.exists(target_path) and os.path.getsize(target_path) > 1024:
        display_path = target_path.replace("\\", "/")
        logging.info(f"✨ [智能跳过] 资产文件已存在于: {display_path}，直接跳过生成进入下一项！")
        return True

    # 1. 载入历史专属会话 URL
    sessions = load_sessions()
    saved_url = sessions.get(char_id)
    
    if saved_url:
        logging.info(f"检测到角色「{char_name}」拥有已缓存的专属会话。正在导入跳转...")
        await agent.navigate(saved_url)
    else:
        logging.info(f"未找到角色「{char_name}」的历史会话，正在开启全新会话...")
        await agent.navigate("https://chatgpt.com/")
        
    # 增加等待时间至 10.0 秒以令 ChatGPT 的 React 历史状态和 DOM 彻底加载和沉淀，100% 避免 race condition
    await asyncio.sleep(10.0)
    
    # 2. 扫描已有大图缓存（做为后面触发 DALL-E 之后寻找新生成图片的基准）
    pre_srcs = await scan_existing_web_images(agent)
    logging.info(f"页面当前大图缓存量: {len(pre_srcs)} 张")
    
    # 3. 运行防虚拟化滚动收集，提取已生成的历史图与 prompt 的对应关系，并进行 Prompt 相似度精准匹配
    # 如果是已有缓存的专属会话，历史记录绝不应为空。如果是空，则很有可能是因为加载延迟，我们将进行重试
    history_pairs = []
    if saved_url:
        for attempt in range(3):
            history_pairs = await scan_conversation_history(agent)
            if history_pairs:
                break
            logging.warning(f"⚠️ 警告：检测到专属会话历史解析为空 (第 {attempt+1}/3 次尝试)，等待 3 秒后重试...")
            await asyncio.sleep(3.0)
    else:
        history_pairs = await scan_conversation_history(agent)
    
    matched_image_src = None
    max_sim = 0.0
    
    for pair in history_pairs:
        sim = get_prompt_similarity(prompt, pair["prompt"])
        if sim > 0.65 and sim >= max_sim: # 使用 >= 保证存在重生成时选取最新一张
            max_sim = sim
            matched_image_src = pair["image"]
            
    if matched_image_src:
        logging.info(f"✨ [历史图智能拾取] 相似度匹配成功 (similarity={max_sim:.2f})！")
        logging.info(f"直接跳过 DALL-E 生图，直存并同步该历史大图: {matched_image_src[:80]}...")
        
        os.makedirs(target_dir, exist_ok=True)
        res = await agent.smart_save(matched_image_src, target_path)
        if res and res.get("status") == "success":
            local_path = target_path.replace("\\", "/")
            sync_new_image_to_json(char_id, img_type, TYPE_LABEL.get(img_type, img_type), local_path, prompt)
            logging.info(f"【成功同步】角色「{char_name}」的「{TYPE_LABEL.get(img_type, img_type)}」（通过匹配拾取）已就绪！")
            return True
        else:
            logging.error(f"历史图直存失败: {res.get('error') if res else '无响应'}，将回退到重新生图流程。")

    # 4. 提交绘图
    # 再次扫描并合并已有大图（防范滚动收集历史对话时在 DOM 中新载入了大量历史图片，导致被误判为新生成的图片）
    post_scroll_srcs = await scan_existing_web_images(agent)
    pre_srcs = set(pre_srcs) | set(post_scroll_srcs)
    
    await trigger_dalle_generation(agent, prompt)
    
    # 4. 如果是新开启的会话，首次发送 Prompt 后立即轮询捕获会话 URL，确保即便后边绘图超时也能完美锁定本角色的专属会话！
    if not saved_url:
        logging.info("新开启会话，正在安全拦截捕获专属聊天 URL...")
        for _ in range(10):
            await asyncio.sleep(1.5)
            url = await agent.evaluate("window.location.href")
            if url and "/c/" in url:
                save_session(char_id, url)
                saved_url = url
                break
                
    # 5. 等待完成
    new_src = await poll_until_image_ready(agent, pre_srcs)
    if new_src == "quota_limit":
        logging.error(f"⚠️ [限额拦截] 检测到生图限额已满，停止当前角色的流水线生成以避免无谓重试。")
        return "quota_limit"
    if new_src == "error" or not new_src:
        logging.error(f"绘图执行出现错误或超时，本次生成失败。")
        return False
        
    # 6. 智能保存大图，绕过 FDM 拦截，直接存入目标文件夹
    logging.info(f"正在通过 smart_save 智能直存图片至: {target_path}")
    os.makedirs(target_dir, exist_ok=True)
    res = await agent.smart_save(new_src, target_path)
    if not res or res.get("status") != "success":
        logging.error(f"图片直存失败: {res.get('error') if res else '无响应'}")
        return False
        
    local_path = target_path.replace("\\", "/")
    
    # 7. 同步回写 JSON 数据库
    sync_new_image_to_json(char_id, img_type, TYPE_LABEL.get(img_type, img_type), local_path, prompt)
    
    logging.info(f"【成功同步】角色「{char_name}」的「{TYPE_LABEL.get(img_type, img_type)}」已全部就绪！")
    return True

async def run_all_pipeline(dry_run: bool, char_id: str = None, img_type: str = None):
    logging.info("=" * 60)
    logging.info(" React 多部位资产自动化流水线启动…")
    
    # 我们为两个角色定义的部位生成计划
    crimson_plan = [
        {
            "char_id": "char_0001_crimson_guardian",
            "char_name": "赤衣守城者",
            "img_type": "main",
            "prompt": "A breathtaking masterfully crafted epic fantasy concept art of the Crimson Wall Guardian. A young, slender East Asian swordsman with highly refined handsome facial features and long wind-blown black hair. He is wearing an incredibly detailed, flowing crimson silk robe designed with elegant layering, adorned with exquisite golden ancient engravings and silver armor plates. He stands heroic and unyielding on a massive, majestic ancient stone fortress wall. In one hand, he holds a beautifully detailed divine sword that glows with faint red aura and intricate runes. The background features a dramatic, glorious sunset with sweeping rays of golden and fiery orange light piercing through epic clouds, casting a warm, rich glow over the endless scenic mystical wasteland below. Particles of dust and glowing embers float in the air, creating a rich, highly detailed cinematic masterpiece, octane render, hyper-realistic textures, 8k resolution."
        },
        {
            "char_id": "char_0001_crimson_guardian",
            "char_name": "赤衣守城者",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Crimson Wall Guardian character from our conversation. Focus on his face and shoulders, capturing his focused, unyielding dark red eyes and messy long black hair. The warm golden light from a dramatic sunset illuminates one side of his face, showing handsome refined facial features, skin texture, and subtle ancient combat markings on his cheek. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0001_crimson_guardian",
            "char_name": "赤衣守城者",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Crimson Wall Guardian character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one calm and focused, one showing a powerful determined war shout, and one tired with a faint, proud smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        }
    ]
    
    midnight_plan = [
        {
            "char_id": "char_0002_midnight_warden",
            "char_name": "午夜值守员",
            "img_type": "main",
            "prompt": "A stunning, highly detailed modern urban mystery cinematic concept art of the Midnight Warden. A slender, delicate young East Asian woman with beautiful focused dark brown eyes, tired yet sharp with noticeable dark circles under them. Her pitch-black mid-length hair is elegantly half-pinned up with the rest flowing naturally over her shoulders. She wears a tailored, neatly buttoned deep navy blue duty uniform. Pinned elegantly on her left chest is a bright, mystical glowing silver duty badge, casting a soft, warm ethereal light onto her detailed, expressive handsome face, showing exquisite skin texture. She stands alone at the end of an atmospheric, dimly lit quiet corridor. Behind her, a mysterious wooden door glows brightly from its cracks with warm golden-amber light. In one hand, she holds a vintage metallic flashlight, casting a sharp beam of light reflecting on the polished marble floor. Cool moonlight white Tyndall beams pierce through window panes, creating a breathtaking high-fidelity contrast, masterpiece, unreal engine 5 render, 8k."
        },
        {
            "char_id": "char_0002_midnight_warden",
            "char_name": "午夜值守员",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Midnight Warden character from the previous image. Focus on her face and shoulders, capturing her tired yet focused expression and the half-pinned dark hair. Pinned on her navy duty uniform, the silver badge glows softly, casting a warm amber light onto her cheek, highlighting highly realistic skin details. Solid, extremely dark, low-contrast studio background. Masterpiece, cinematic lighting, 8k."
        },
        {
            "char_id": "char_0002_midnight_warden",
            "char_name": "午夜值守员",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Midnight Warden character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one tired but calm, one alert with focused eyes, and one showing a rare, gentle subtle smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        }
    ]

    sandstorm_plan = [
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "main",
            "prompt": "A breathtaking epic post-apocalyptic concept art of the Sandstorm Pilgrim. A mature, weathered East Asian ascetic monk with deep, wise facial lines and short grizzled hair tied with a faded red band. He is wearing a coarse, heavily patched sand-swept gray linen cloak over rugged survival garments. He walks barefoot heroically across a vast, barren desert wasteland during a dramatic sandstorm. In one hand, he holds a detailed heavy brass staff adorned with ancient bronze wind chimes that sway in the wind. The background features giant sand dunes, a hazy sun struggling to pierce through thick amber dust clouds, casting a majestic and melancholic warm rim light on his silhouette. Cinematic masterpiece, hyper-realistic textures, octane render, 8k resolution."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Sandstorm Pilgrim character from our conversation. Focus on his face and shoulders, capturing his deep, wise grey eyes and weathered facial features. The warm, hazy amber light from the sandstorm illuminates one side of his face, highlighting his skin texture and dust on his cheek. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Sandstorm Pilgrim character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one calm and meditative, one showing a determined yell against the wind, and one displaying a rare, serene and peaceful smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Sandstorm Pilgrim character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his coarse gray linen cloak and rugged survival garments. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Sandstorm Pilgrim character from our conversation, but wearing an alternative survival outfit: a heavy sand-shielding leather armor, thick thermal wraps around his torso, and a protective respirator mask hanging around his neck. Full-body view, standing heroically on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed weapon prop design sheet of the Sandstorm Pilgrim's heavy brass staff. Show the staff from two angles, highlighting the intricate ancient bronze wind chimes, wrapped leather grip, and worn metallic textures. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed landscape scene concept art. An ancient, half-buried mystical sand temple ruins under a massive brewing amber dust storm, with columns glowing with faint gold runes. Ethereal golden sun rays piercing through the thick clouds, casting a dramatic, glorious rim light over the desolate ruins. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0003_sandstorm_pilgrim",
            "char_name": "风沙朝圣者",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Sandstorm Pilgrim character from our conversation. He stands barefoot in his signature patched cloak, holding his brass staff, looking forward with wise grey eyes. Solid, extremely dark, low-contrast studio background. Masterpiece, hyper-realistic textures, 8k."
        }
    ]

    neon_plan = [
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "main",
            "prompt": "A masterpiece cyberpunk cinematic concept art of the Neon Shadow Hacker. A cool young East Asian female hacker with highly detailed expressive facial features and asymmetrical glowing pink and purple hair. Her right eye is covered by a sleek, translucent yellow holographic tactical visor. She wears a matte-black premium technical raincoat over a dark bodysuit with subtle glowing circuit lines. She is crouched dynamically on a concrete ledge high above a futuristic neon-drenched metropolis under heavy rain. Her left arm, a highly detailed black carbon-fiber cybernetic prosthetic, is releasing glowing blue neural cables into a hacking node. The background features towering skyscrapers covered in massive holographic advertisements, casting vibrant neon reflections of pink, cyan, and gold onto the wet surfaces and puddles. Photorealistic, unreal engine 5 render, highly detailed, 8k resolution."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Neon Shadow Hacker character from our conversation. Focus on her face and shoulders, capturing her focused, cool expression and asymmetrical pink and purple hair. Pinned on her technical raincoat, the yellow translucent visor glows softly, casting a warm light onto her cheek, highlighting highly realistic skin details. Solid, extremely dark, low-contrast studio background. Masterpiece, cinematic lighting, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Neon Shadow Hacker character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one cool and indifferent, one showing a smirk with a raised eyebrow, and one showing a focused, intense gaze while hacking. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Neon Shadow Hacker character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her matte-black technical raincoat and tactical visor. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Neon Shadow Hacker character from our conversation, but wearing an alternative stealth outfit: a tight, high-mobility matte-black stealth bodysuit with glowing violet energy seams, and sleek tactical boots, without her bulky raincoat. Full-body view, standing dynamically on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Neon Shadow Hacker's tactical gear: her yellow translucent visor and the carbon-fiber cybernetic prosthetic arm showing its internal glowing blue neural cables. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "scene",
            "prompt": "Now, draw a breathtaking cyberpunk city street scene concept art. High-altitude view of towering skyscrapers covered in massive glowing pink, purple and cyan holographic advertisements under heavy rain. Wet streets and puddles reflecting the vibrant neon lights, creating a highly detailed cinematic atmospheric masterpiece, unreal engine 5 render, 8k."
        },
        {
            "char_id": "char_0004_neon_hacker",
            "char_name": "霓虹潜行者",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Neon Shadow Hacker character from our conversation. She stands in her signature raincoat, arm extended, visor glowing, in a cool stealth pose. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]
    astrolabe_plan = [
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "main",
            "prompt": "A masterfully crafted epic fantasy concept art of the Astrolabe Archivist. A slender, handsome young East Asian male scholar with short, messy silver-gray hair. His eyes are elegantly covered with a fine, star-embroidered silk white blindfold. He is wearing elaborate, layered midnight-blue scholar robes adorned with intricate gold-threaded celestial constellations and constellations embroidery. He stands inside a soaring, dark gothic archives library, holding a highly detailed, glowing mechanical gold and silver astrolabe floating above his open palms. Shimmering, ethereal blue-and-gold stardust and glowing cosmic charts float gently around him, passing through hovering crystal magnification lenses. Masterpiece, unreal engine 5 render, highly detailed, 8k resolution."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Astrolabe Archivist character from our conversation. Focus on his face and shoulders, capturing his star-embroidered white blindfold, silver-gray hair, and handsome refined features. The soft ethereal blue and gold micro-lights from his floating astrolabe cast gentle stellar glimmers onto his cheeks, highlighting realistic skin details. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Astrolabe Archivist character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one serene and calm, one with a subtle focused frown as if deep in observation, and one showing a faint, gentle and warm smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Astrolabe Archivist character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his midnight-blue scholar robes and star-embroidered white blindfold. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Astrolabe Archivist character from our conversation, but wearing an alternative mystical high-priest outfit: a majestic white and gold ceremonial robe with flowing stardust silk sleeves, holding a silver celestial sceptre, without his dark scholar robes. Full-body view, standing dynamically on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed artifact design sheet of the Astrolabe Archivist's floating mechanical gold and silver astrolabe. Show it from two angles, highlighting the intricate rotating celestial gears, glowing crystal runes, and metallic textures. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed gothic grand archive library scene concept art. A soaring cathedral-like chamber with massive towering dark-wood bookshelves, mystical glowing blue celestial stardust charts and constellations projecting in mid-air, casting a dramatic, glorious rim light over ancient scrolls. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0005_astrolabe_archivist",
            "char_name": "星轨记录员",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Astrolabe Archivist character from our conversation. He stands in his signature midnight-blue scholar robes, holding the glowing floating astrolabe, looking serene and powerful. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]
    
    rust_mechanic_plan = [
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "main",
            "prompt": "A masterfully crafted epic wasteland action concept art of the Rustland Reconstructor. An energetic young East Asian tomboy mechanic with messy short coffee-brown hair and a patch of black motor grease playfully smudged on her left cheek. She wears protective dusty work goggles pushed up on her forehead and a rugged, sleeveless grease-stained khaki work jumpsuit. She is sitting dynamically inside a cluttered desert scrap-iron workshop, operating a massive, heavily customized rusted scrap-iron exopower mechanical claw that glows with intense, bright orange fiery engine exhaust and white steam. Scrap-metal gears, wrenches, and engine parts lie scattered all around her. The background features a dramatic orange dusty sunset casting rich, glowing rim light over the desert ruins. Masterpiece, unreal engine 5 render, photorealistic, 8k resolution."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Rustland Reconstructor character from our conversation. Focus on her face and shoulders, capturing her messy short brown hair, grease-smudged cheek, and bright amber eyes. Pushed up on her forehead are her work goggles. Soft orange glowing highlights from her workshop engines reflect onto her skin, showing highly realistic skin details. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Rustland Reconstructor character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one bright and energetic with an open-mouthed laugh, one intensely focused and alert, and one showing a cute, playful smirk with a wink. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Rustland Reconstructor character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her work goggles, sleeveless khaki jumpsuit, and tactical gloves. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Rustland Reconstructor character from our conversation, but wearing an alternative heavy scavenger power armor: a bulkier iron-plated exoskeleton suit with bright glowing copper tubes, and protective heavy steel boots, with her goggles pulled down over her eyes. Full-body view, standing dynamically on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Rustland Reconstructor's heavy exopower bionic claw. Show the giant rusted scrap-iron claw from two angles, highlighting the complex hydraulic gears, exposed copper wiring, and bright orange engine exhaust venting. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "scene",
            "prompt": "Now, draw a breathtaking post-apocalyptic desert scrap-iron workshop scene concept art. A cluttered workshop filled with mountains of rusted metal plates, scattered gears, steam pipes venting, and a giant scrap engine in the center. Heavy sun rays piercing through the dusty air, casting intense warm rim light over the chaotic workspace. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0006_rust_mechanic",
            "char_name": "废铁重构师",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Rustland Reconstructor character from our conversation. She stands dynamically in her work jumpsuit next to her giant mechanical claw, smiling confidently with amber eyes. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]
    
    rust_sniper_plan = [
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "main",
            "prompt": "A masterfully crafted epic post-apocalyptic cinematic concept art of the Rustland Silent Scout. A tall, handsome young East Asian marksman with highly refined sharp facial features and wind-blown short black hair. His right eye is replaced by an intricate, glowing mechanical cybernetic gear assembly glowing with cool cyan light, custom-built from scrap brass by the Reconstructor. He wears a rugged, dust-swept tactical black hooded cape over worn combat plates. He is lying alertly on a decaying, rusted scrap-iron railway bridge above a scenic desert canyon. In his hands, he grips a massive two-meter long heavy futuristic electromagnetic scanning device meticulously welded from scrap steel pipes and copper coils that hums with faint blue electric arcs. The background features a sweeping, cinematic yellow sandstorm engulfing towering metal ruins under a dramatic amber-red dusty sunset. Rich rim lighting, masterpiece, photorealistic textures, octane render, 8k resolution."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Rustland Silent Scout character from our conversation. Focus on his face and shoulders, capturing his left cold dark eye and the intricate glowing cyan cybernetic gear assembly replacing his right eye. Dust on his cheek and wind-blown short black hair. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Rustland Silent Scout character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one cold and expressionless, one with eyes narrowed in sharp focus, and one showing a subtle, tired half-smile. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Rustland Silent Scout character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his rugged black hooded cape, worn combat plates, and tactical boots. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Rustland Silent Scout character from our conversation, but wearing an alternative survival outfit: a dust-shielding sand-colored ghillie poncho, lightweight combat harness, and protective tactical mask hanging around his neck. Full-body view, standing on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed artifact design sheet of the Rustland Silent Scout's gear: his massive electromagnetic scanning sniper rifle welded from scrap steel pipes and copper coils. Show it from two angles, highlighting the copper wiring and faint blue electric arcs. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed post-apocalyptic cinematic scene concept art. A decaying, rusted scrap-iron railway bridge spanning across a deep scenic desert canyon under a sweeping yellow sandstorm and dramatic sunset. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0007_rust_sniper",
            "char_name": "尘沙潜行卫",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Rustland Silent Scout character from our conversation. He stands alertly in his black hooded cape, holding his massive electromagnetic sniper rifle, with his cyan cybernetic eye glowing softly. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]
    
    rust_apprentice_plan = [
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "main",
            "prompt": "A breathtaking masterfully crafted post-apocalyptic cinematic concept art of the young Rustland Workshop Apprentice. A cheerful, slightly clumsy teenage East Asian boy with short messy black hair and a dirt smudge on his nose. He wears an oversized, loose-fitting khaki mechanic jumpsuit with one shoulder strap hanging down, heavy brown leather work gloves, and steel-toed boots. He carries a heavy canvas bag filled with various rusted metal wrenches and gears on his back. He is standing dynamically in a cluttered scrap yard, holding a giant copper gear, looking proud and energetic. Heavy sun rays piercing through the dusty air, casting intense warm rim light, unreal engine 5 render, highly detailed, photorealistic textures, 8k resolution."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same young Rustland Workshop Apprentice character from our conversation. Focus on his face and shoulders, capturing his cheerful expression, short messy black hair, and a dirt smudge on his nose. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same young Rustland Workshop Apprentice character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one bright and smiling, one with a confused look scratching his head, and one determined and shouting with grit. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same young Rustland Workshop Apprentice character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his oversized khaki jumpsuit with one strap hanging down and heavy leather gloves. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same young Rustland Workshop Apprentice character from our conversation, but wearing an alternative work outfit: grease-stained denim overalls over a bright orange t-shirt, thick safety welding goggles on his forehead, and utility tool belt. Full-body view, standing on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed prop design sheet of the young Rustland Workshop Apprentice's canvas tool bag and his oversized copper gear. Show them from two angles, highlighting the rusted metallic textures. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed post-apocalyptic scrap yard scene concept art. Mountains of rusted metal plates, old engines, scattered gears, and dust floating in dramatic sun rays. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0008_rust_apprentice",
            "char_name": "重工坊学徒",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same young Rustland Workshop Apprentice character from our conversation. He stands proudly in his oversized khaki jumpsuit, carrying his canvas tool bag and holding a giant copper gear, smiling confidently. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]
    
    rust_nomad_plan = [
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "main",
            "prompt": "A desolate, highly detailed character concept art in a photorealistic cinematic style showing a silent Wasteland Nomad. A thin, weary Middle Eastern man covered in heavily patched dusty gray and brown linen rags and sandproof face wrappings. He carries an old, dented brass water jar in both hands, walking wearily through a toxic yellow desert sandstorm. Behind him are scattered ruins of half-buried rusted steel containers, heavy dust atmosphere, dramatic setting sunset casting majestic rim lighting, unreal engine 5 render, highly detailed, masterpiece, 8k resolution."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up high-fidelity portrait of the exact same Wasteland Nomad character from our conversation. Focus on his face and shoulders, capturing his weary Middle Eastern features, dark alert eyes, and sandproof face wrappings. Dust and dirt smudged on his face. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Wasteland Nomad character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one alert and watchful, one weary with half-closed eyes, and one displaying a rare, subtle peaceful gaze. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Wasteland Nomad character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his heavily patched dusty gray and brown linen rags and sandproof face wrappings. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Wasteland Nomad character from our conversation, but wearing an alternative scavenger outfit: a hooded sand-cloak reinforced with scrap metal plates, thick survival wraps around his limbs, and a worn tactical satchel. Full-body view, standing on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed artifact design sheet of the Wasteland Nomad's gear: his old dented brass water jar and a walking staff wrapped in linen. Show them from two angles, highlighting the weathered textures and dents. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed post-apocalyptic desert landscape scene concept art. Desolate sand dunes, ruins of half-buried rusted steel containers under a toxic yellow sandstorm and majestic setting sunset. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0009_rust_nomad",
            "char_name": "荒原流民",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Wasteland Nomad character from our conversation. He stands wearily in his patched linen rags, holding his dented brass water jar, looking forward with resilient dark eyes. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]
    
    rust_warlord_plan = [
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "main",
            "prompt": "A masterpiece post-apocalyptic cinematic concept art of the Rustland Warlord. A massive, muscular East Asian warlord with a scarred face and cold, ruthless expression. His right eye is replaced by a crude mechanical bionic eye glowing with intense red light. His entire right arm is a massive, heavily customized industrial hydraulic cybernetic limb made from rusted iron and copper pipes, venting black soot and faint orange sparks. He is wearing heavy, intimidating scrap-metal power armor welded from truck panels and steel grids, decorated with warning yellow stripes. He stands heroic and tyrannical on a watchtower overlooking a raider camp filled with modified spiked vehicles. Behind him, a giant rusted aircraft carrier wreckage looms under a dramatic dusty red sunset, casting a glorious and oppressive rim light. Masterpiece, unreal engine 5 render, highly detailed textures, 8k resolution."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Rustland Warlord character from our conversation. Focus on his face and shoulders, capturing his scarred face, silver hair, and the crude bionic eye glowing with intense red light. Black soot smudges on his cheeks. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Rustland Warlord character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one cold and sneering, one letting out a terrifying roaring laugh, and one with narrowed eyes in silent rage. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Rustland Warlord character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his scrap-metal power armor and hydraulic arm. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Rustland Warlord character from our conversation, but wearing an alternative casual scavenger warlord outfit: a long, grease-stained leather trench coat over a ribbed black tank top, heavy combat trousers, and steel-toed boots, while keeping his hydraulic bionic arm. Full-body view, standing on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Rustland Warlord's weapons: his massive spiked hydraulic power hammer and his custom diesel-powered mechanical arm showing hydraulic pistons and fuel tubes. Show them from two angles, highlighting the grease-stained rusted metal textures. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed post-apocalyptic raider camp scene concept art. A fortress built from a massive, decaying aircraft carrier wreckage, surrounded by watchtowers, barbed wire, and spiked desert vehicles. Billowing black smoke and dramatic amber sunset casting long, dark shadows. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0010_rust_warlord",
            "char_name": "铁血军阀",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Rustland Warlord character from our conversation. He stands triumphantly in his scrap-metal power armor, holding his spiked hydraulic hammer, his red mechanical eye glowing menacingly. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]

    rust_scavenger_queen_plan = [
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "main",
            "prompt": "A masterpiece post-apocalyptic cinematic concept art of the Scavenger Queen. A slender and agile young East Asian woman with a cunning and sharp gaze. She has short, styled silver hair with glowing neon-green dyed tips. She wears a dark leather tunic reinforced with copper scales, underneath a worn, chemical-resistant dark green hooded hazard cloak that flows in the wind. Her lower face is covered by a detailed brass respirator mask with three circular filters. She stands dynamically amidst the towering rusted ruins of a ruined chemical factory. In her hands, she aims a detailed custom folding metallic crossbow that glows with bubbling, radioactive neon-green liquid vials. The background features acid rain falling through thick yellow clouds, with green toxic puddles reflecting a bleak setting sun casting a sickly warm glow. Cinematic, hyper-realistic, masterpiece, 8k resolution."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Scavenger Queen character from our conversation. Focus on her face and shoulders, capturing her sharp green eyes, silver-green hair, and the detailed brass respirator mask. Acid rain droplets on her cloak. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Scavenger Queen character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side (without respirator mask): one smiling cunningly, one showing an angry cold glare, and one displaying a calculated smirk. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Scavenger Queen character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her dark green hooded cloak and brass respirator. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Scavenger Queen character from our conversation, but wearing an alternative scavenger outfit: a tight-fitting black environmental hazard jumpsuit, reinforced knee pads and tactical harness, and a glowing green chemical canister strapped to her back, without her large green cloak. Full-body view, standing on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Scavenger Queen's weapons: her custom folding metallic crossbow and a set of glass vials filled with bubbling neon-green acid. Show them from two angles, highlighting the metallic wear and glowing green liquid. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed post-apocalyptic chemical factory ruins scene concept art. Towering corroded distillation towers, glowing toxic green acid swamps, acid rain falling from yellow chemical smog under a bleak setting sun. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0011_scavenger_queen",
            "char_name": "拾荒女皇",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Scavenger Queen character from our conversation. She stands agilely in her green hooded cloak, holding her folding crossbow, her green eyes glowing slightly in the toxic haze. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        }
    ]

    boundary_investigator_plan = [
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "main",
            "prompt": "A masterpiece urban mystery concept art of the Boundary Investigator. A handsome, slender young East Asian male detective with short messy ink-blue hair. He wears a gold-rimmed monocle on his left eye, showing sharp, intelligent eyes. He is dressed in a tailored deep-gray double-breasted trench coat with a black vest and crimson tie underneath. He stands in a rainy, dark alleyway at midnight, holding a glowing vintage vacuum-tube radio in his gloved hands. The radio glows with an eerie teal-green aura, casting faint wave ripples in the foggy air. Background features yellow glowing streetlamps reflecting on wet asphalt, cinematic shadows, octane render, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Boundary Investigator character from our conversation. Focus on his face and shoulders, capturing his messy ink-blue hair, the gold-rimmed monocle on his left eye, and his calm, sharp expression. Rain droplets on his coat. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Boundary Investigator character from our conversation. Show him on a solid, clean dark gray background with three different facial expressions side-by-side: one calm and calculating, one with a subtle cynical smirk under his monocle, and one looking surprised/tense while listening to the radio. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Boundary Investigator character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. He is wearing his deep-gray double-breasted trench coat. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "outfit",
            "prompt": "Now, draw the exact same Boundary Investigator character from our conversation displaying three different outfits side-by-side on a plain clean dark gray background: on the left, his default deep-gray trench coat uniform; in the middle, his alternative private investigator waistcoat outfit (a dark blue waistcoat vest over a rolled-up white shirt and dark trousers, without his trench coat); on the right, his detective field uniform (a dark utility windbreaker jacket with tactical pockets). Show three side-by-side full-body views, standing on a solid clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Boundary Investigator's gear: his vintage vacuum-tube radio with glowing teal-green indicator lights and dials, and his leather-bound investigator notebook. Show them from two angles. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed urban mystery scene concept art. A dark, rain-slicked city alleyway at midnight, glowing yellow streetlamps, dark puddles reflecting the lights, and a mysterious door outlined in faint glowing teal-green energy in the shadows. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art showing the Boundary Investigator debugging his glowing vintage radio, standing on a rainy urban building rooftop. Waves of teal-green radio frequency lines ripple across the sky, with the dark cityscape reflecting off rain puddles. High polish, dramatic rim lighting, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Boundary Investigator: one showing close-up rain reflections on a dark asphalt road, one showing glowing copper vacuum tubes of a vintage radio, one showing a gold-rimmed monocle resting on an open investigation notebook, and one showing ink-blue curls of hair under dim yellow streetlights. Eerie, mysterious tone, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Boundary Investigator in 3 study sketches: adjusting his monocle, tuning his hand-held radio, and walking down a dark corridor. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Boundary Investigator character from our conversation. He stands alert in his trench coat, holding his glowing vintage radio, looking towards the viewer with a knowing smile. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Boundary Investigator showing full-body front, side, and back views. Standing neutrally in his deep-gray double-breasted trench coat. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Boundary Investigator on one clean sheet: walking with a flashlight, kneeling to check a rain puddle, tuning his radio close to his ear, running in warning/alarm, and leaning against a brick wall with a cold smirk. Solid clean dark gray background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Boundary Investigator in a clean grid: calm, calculating, a sharp smirk, showing tension while listening to static, tired/exhausted with dark circles, a subtle warning look, coughing in wet cold weather, and focused determination. Clean dark gray background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Boundary Investigator's features: his gold-rimmed monocle (left eye), his old vacuum-tube radio's speaker grill and teal-green wave dial, the fabric texture of his deep-gray trench coat collar, the leather gloves on his hands, and his scrawled handwritten notes. Clean light gray background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "materialPalette",
            "prompt": "A material and color palette sheet for the Boundary Investigator: fabric swatches of deep-gray wool, ink-blue hair sample, gold monocle metal shine, crimson tie silk, and the teal-green light glow of his radio. Clean design layout, plain gray background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "outfitBreakdown",
            "prompt": "An outfit breakdown sheet for the Boundary Investigator: showing separate layers of his clothing: deep-gray trench coat, black waistcoat vest, white collared shirt with crimson tie, dark trousers, and leather gloves. Clean layout, plain light background."
        },
        {
            "char_id": "char_0012_boundary_investigator",
            "char_name": "界线调查员",
            "img_type": "damageState",
            "prompt": "Show 3 full-body versions of the Boundary Investigator: clean/default, battle-worn with dust smudges and torn coat sleeve, and heavily damaged with shattered monocle, blood-stained bandages on his forehead, and a cracked vintage radio. Solid clean dark gray background."
        }
    ]

    lantern_keeper_plan = [
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "main",
            "prompt": "A breathtaking gothic fantasy concept art of the Eternal Lantern Keeper. An elegant, young woman with refined features and pale skin. Her eyes glow with a soft starry gold light, and she has long flowing silver-white hair with faint gold reflections. She wears layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, and a sheer black cape over her shoulders. She stands inside a silent, towering cathedral library ruins, holding a gothic black-iron candle lantern. Inside the lantern, a floating bright blue stellar flame burns, shedding glowing stardust particles. Dark atmospheric archives in the background, cinematic rim lighting, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "portrait",
            "prompt": "Now, draw a close-up portrait of the exact same Eternal Lantern Keeper character from our conversation. Focus on her face and shoulders, capturing her starry gold eyes, silver-white hair, and her calm, compassionate expression. Star dust particles floating around. Solid, extremely dark, low-contrast studio background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "expression",
            "prompt": "Now, draw an expression sheet of the exact same Eternal Lantern Keeper character from our conversation. Show her on a solid, clean dark gray background with three different facial expressions side-by-side: one serene and peaceful, one showing gentle sorrow with a starry gold tear, and one with a serious, guarding expression. High-fidelity details, professional character model sheet, masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "turnaround",
            "prompt": "Now, draw a professional character turnaround model sheet of the exact same Eternal Lantern Keeper character from our conversation. Show three full-body views: front, side, and back, standing in a neutral pose. She is wearing her midnight-blue gothic robes and black cape. Solid, clean dark gray background. High-fidelity details, masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "outfit",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Eternal Lantern Keeper (永夜守灯人)\nGender / age impression: young woman, elegant, pale skin, serene and holy presence\nBody shape: slender and graceful silhouette\nFace: delicate refined face, calm and compassionate expression\nHair: long flowing silver-white hair with faint gold reflections\nEyes: gold eyes that glow with soft starry light\nOutfit: layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, sheer black cape over shoulders\nAccessories / weapon: gothic black-iron candle lantern containing a floating bright blue stellar flame that sheds glowing stardust particles\nColor palette: midnight-blue, silver-white, gold, deep black, bright blue stellar flame highlights\nFixed traits that must never change: silver-white hair, gold-glowing eyes, midnight-blue gothic robes with gold embroidery, black-iron lantern with blue flame, serene holy expression\n\nCurrent asset goal:\nGenerate an outfit variant image. Show three different outfits side-by-side: on the left, her default midnight-blue gothic robes; in the middle, her alternative ceremonial white priestess gown with silver embroidery and a silver crescent crown; on the right, her archival scholar robes (a light blue and gray velvet gown with wide sleeves).\n\nStyle:\nGothic fantasy character concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body views of the same character standing neutrally. Keep the character clearly readable. Avoid unnecessary extra characters.\n\nBackground:\nPlain clean dark gray background.\n\nConstraints:\nKeep the same face, hairstyle, color palette, body shape, and signature accessories.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "prop",
            "prompt": "Now, draw a high-fidelity detailed design sheet of the Eternal Lantern Keeper's gear: her gothic black-iron lantern with a floating bright blue stellar flame, and a heavy, leather-bound ancient tome of destiny. Show them from two angles. Solid, clean dark gray background. Masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "scene",
            "prompt": "Now, draw a stunning, highly detailed dark fantasy scene concept art. Towering stone arches of a cathedral library in ruins, ancient bookshelves stretching into darkness, with floating glowing constellation maps and stardust drifting in the air. Cinematic, hyper-realistic, masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "cover",
            "prompt": "A cinematic vertical cover art showing the Eternal Lantern Keeper walking down the giant, cathedral-like library ruins. She holds her glowing blue-flamed black-iron lantern high, casting long shadows on towering book archives, as glowing stellar constellations float above her. High polish, masterpiece, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "moodboard",
            "prompt": "A moodboard collage of 4 panels for the Eternal Lantern Keeper: one showing ancient, dusty leather-bound books, one showing a bright blue candle flame floating inside a gothic iron cage, one showing golden star constellations mapping on dark velvet fabric, and one showing long silver-white hair reflecting soft gold light. Sacred, gothic, mysterious tone, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "sketch",
            "prompt": "A concept sketch sheet of monochrome pencil drawings showing the Eternal Lantern Keeper in 3 study sketches: holding the lantern forward, praying, and looking down at a giant open book of destiny. Clean hand-drawn lines, traditional concept art sketch style, plain light background."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "fullBody",
            "prompt": "Now, draw a full-body cinematic splash art of the exact same Eternal Lantern Keeper character from our conversation. She stands gracefully in her midnight-blue robes, holding her glowing lantern, looking forward with compassionate gold eyes. Solid, extremely dark, low-contrast studio background. Masterpiece, highly detailed, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "modelSheet",
            "prompt": "A clean model sheet of the Eternal Lantern Keeper showing full-body front, side, and back views. Standing neutrally in her midnight-blue gothic priestess robes. Even lighting, solid clean light gray background, no dramatic shadows, 8k."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "poseSheet",
            "prompt": "Show 5 poses of the Eternal Lantern Keeper on one clean sheet: walking gracefully with her lantern, holding the lantern high to examine a wall, kneeling to read an ancient tome, raising her hand to cast a star-barrier, and floating slightly in a state of holy meditation. Solid clean dark gray background."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "expressionSheet",
            "prompt": "An expression sheet showing 8 bust portraits of the Eternal Lantern Keeper in a clean grid: serene, gentle sorrow with a golden tear, serious guarding look, eyes closed in silent prayer, calm warning, surprised by invader, exhausted/fading light, and compassionate gentle gaze. Clean dark gray background."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "detailSheet",
            "prompt": "A clean detail sheet showing close-up panels of the Eternal Lantern Keeper's features: her starry gold eyes, her long silver hair with gold strings, the intricate star-map embroidery on her midnight-blue robe skirt, and the gothic black-iron lantern's candle flame. Clean light gray background."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "materialPalette",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Eternal Lantern Keeper (永夜守灯人)\nGender / age impression: young woman, elegant, pale skin, serene and holy presence\nBody shape: slender and graceful silhouette\nFace: delicate refined face, calm and compassionate expression\nHair: long flowing silver-white hair with faint gold reflections\nEyes: gold eyes that glow with soft starry light\nOutfit: layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, sheer black cape over shoulders\nAccessories / weapon: gothic black-iron candle lantern containing a floating bright blue stellar flame that sheds glowing stardust particles\nColor palette: midnight-blue, silver-white, gold, deep black, bright blue stellar flame highlights\nFixed traits that must never change: silver-white hair, gold-glowing eyes, midnight-blue gothic robes with gold embroidery, black-iron lantern with blue flame, serene holy expression\n\nCurrent asset goal:\nGenerate a material and color palette sheet. Show swatches of midnight-blue velvet, silver-white hair sample, starry gold glowing paint, black iron metal texture, and the bright blue stellar flame beside a neutral front view of the character.\n\nStyle:\nGothic fantasy character concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design-board layout showing the character alongside neatly arranged material swatches.\n\nBackground:\nPlain gray background.\n\nConstraints:\nKeep the same face, hairstyle, outfit logic, color palette, body shape, and signature accessories.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "outfitBreakdown",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Eternal Lantern Keeper (永夜守灯人)\nGender / age impression: young woman, elegant, pale skin, serene and holy presence\nBody shape: slender and graceful silhouette\nFace: delicate refined face, calm and compassionate expression\nHair: long flowing silver-white hair with faint gold reflections\nEyes: gold eyes that glow with soft starry light\nOutfit: layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, sheer black cape over shoulders\nAccessories / weapon: gothic black-iron candle lantern containing a floating bright blue stellar flame that sheds glowing stardust particles\nColor palette: midnight-blue, silver-white, gold, deep black, bright blue stellar flame highlights\nFixed traits that must never change: silver-white hair, gold-glowing eyes, midnight-blue gothic robes with gold embroidery, black-iron lantern with blue flame, serene holy expression\n\nCurrent asset goal:\nGenerate an outfit breakdown sheet. Show separate layers and components of her clothing: the outer midnight-blue velvet priestess robes, the black lace cape, the silver crescent crown, and the heavy leather-bound ancient tome of destiny.\n\nStyle:\nGothic fantasy character concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nClean design board layout showing the clothes laid out and separated clearly.\n\nBackground:\nPlain light background.\n\nConstraints:\nKeep all parts consistent with the original character design.\nDo not redesign the character.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        },
        {
            "char_id": "char_0013_lantern_keeper",
            "char_name": "永夜守灯人",
            "img_type": "damageState",
            "prompt": "Use case: stylized-concept\nAsset type: character asset for a reusable character pool\n\nPrimary request:\nCreate a high-quality character asset image for the following character. The goal is consistency and future reuse, not a one-off random illustration.\n\nCharacter lock:\nName: The Eternal Lantern Keeper (永夜守灯人)\nGender / age impression: young woman, elegant, pale skin, serene and holy presence\nBody shape: slender and graceful silhouette\nFace: delicate refined face, calm and compassionate expression\nHair: long flowing silver-white hair with faint gold reflections\nEyes: gold eyes that glow with soft starry light\nOutfit: layered midnight-blue gothic robes with intricate gold star-map embroidery on the skirt, sheer black cape over shoulders\nAccessories / weapon: gothic black-iron candle lantern containing a floating bright blue stellar flame that sheds glowing stardust particles\nColor palette: midnight-blue, silver-white, gold, deep black, bright blue stellar flame highlights\nFixed traits that must never change: silver-white hair, gold-glowing eyes, midnight-blue gothic robes with gold embroidery, black-iron lantern with blue flame, serene holy expression\n\nCurrent asset goal:\nGenerate damage state variants. Show 3 full-body versions of the same character: clean/default, battle-worn with tattered robe hem and dusty cape, and heavily damaged with her body half-translucent and fading, a cracked glass lantern, and golden stellar tears flowing.\n\nStyle:\nGothic fantasy character concept art, high-fidelity design sheet, detailed fabric and material rendering, coherent design language, consistent facial identity, production-ready asset.\n\nComposition:\nShow three side-by-side full-body versions of the character.\n\nBackground:\nSolid clean dark gray background.\n\nConstraints:\nDo not change the costume into a new outfit. Keep the same identity.\nNo text, no watermark, no logo, no extra limbs, no bad hands, no distorted face, no random new weapons."
        }
    ]
    
    full_plan = crimson_plan + midnight_plan + sandstorm_plan + neon_plan + astrolabe_plan + rust_mechanic_plan + rust_sniper_plan + rust_apprentice_plan + rust_nomad_plan + rust_warlord_plan + rust_scavenger_queen_plan + boundary_investigator_plan + lantern_keeper_plan
    
    # 动态为每一项注入其在对应角色子计划中的绝对位置 absolute_idx
    char_counters = {}
    for t_item in full_plan:
        c_id = t_item["char_id"]
        char_counters.setdefault(c_id, 0)
        t_item["absolute_idx"] = char_counters[c_id]
        char_counters[c_id] += 1
        
    # 动态过滤条件
    if char_id:
        full_plan = [task for task in full_plan if task["char_id"] == char_id]
        logging.info(f"已应用角色过滤条件: {char_id} (当前剩余 {len(full_plan)} 个生成项)")
    if img_type:
        full_plan = [task for task in full_plan if task["img_type"] == img_type]
        logging.info(f"已应用部位类型过滤条件: {img_type} (当前剩余 {len(full_plan)} 个生成项)")
        
    if not full_plan:
        logging.warning("⚠️ 过滤后的生成任务列表为空！请检查 --char-id 或 --type 是否正确。")
        return
        
    if dry_run:
        logging.info("当前处于「干跑模式」，仅打印待生成的过滤部位清单：")
        for idx, item in enumerate(full_plan):
            logging.info(f"  {idx+1}. 角色「{item['char_name']}」 -> 部位: {TYPE_LABEL.get(item['img_type'], item['img_type'])}")
            logging.info(f"     Prompt: {item['prompt'][:80]}...")
        logging.info("干跑结束。")
        return
        
    agent = BrowserAgent(WS_URL)
    if not await agent.connect():
        return
        
    try:
        await agent.init("多维度部位自动化同步流水线")
        
        # 依次执行各部位的生成
        for step_idx, task in enumerate(full_plan):
            logging.info("=" * 60)
            logging.info(f"正在执行任务流水线 [{step_idx + 1}/{len(full_plan)}]")
            
            success = False
            for attempt in range(1, 3):
                try:
                    res = await generate_character_part(
                        agent,
                        task["char_id"],
                        task["char_name"],
                        task["img_type"],
                        task["prompt"],
                        task["absolute_idx"]
                    )
                    if res == "quota_limit":
                        logging.critical("🚨 [额度已达上限] 触发 OpenAI 生图频率或额度限制，系统将直接强行终止并退出整个绘图流水线！")
                        return
                    if res:
                        success = True
                        break
                    else:
                        logging.warning(f"第 {attempt} 次生成未成功，等待 5 秒后重试...")
                        await asyncio.sleep(5)
                except Exception as ex:
                    logging.error(f"执行发生异常: {ex}", exc_info=True)
                    await asyncio.sleep(5)
            
            if not success:
                logging.error(f"任务 [{task['char_name']} - {task['img_type']}] 遭遇不可恢复失败，跳过。")
            
            # 留出 3 秒缓冲给用户/AI观察
            await asyncio.sleep(3)
            
        logging.info("=" * 60)
        logging.info("🎉 恭喜！所选角色、部位维度的资产绘图任务已全部完成！")
        
    finally:
        await agent.close()

def main():
    global OUTPUT_ROOT
    parser = argparse.ArgumentParser(description="多部位一致性资产自动生成与回写引擎")
    parser.add_argument("--dry-run", action="store_true", help="干跑模式，仅打印计划")
    parser.add_argument("--char-id", type=str, default=None, help="过滤指定角色 ID (如 char_0001_crimson_guardian)")
    parser.add_argument("--type", type=str, default=None, help="过滤指定图片部位类型 (如 main, portrait, expression)")
    parser.add_argument("--output-root", type=str, default=None, help="覆盖图片输出归档根目录")
    args = parser.parse_args()
    
    if args.output_root:
        OUTPUT_ROOT = args.output_root.replace("\\", "/")
        logging.info(f"✨ 命令行参数指定覆盖输出目录为: {OUTPUT_ROOT}")
    
    try:
        asyncio.run(run_all_pipeline(args.dry_run, args.char_id, args.type))
    except KeyboardInterrupt:
        logging.info("\n用户手动终止。")
    except Exception as e:
        logging.critical(f"严重未捕获错误: {e}", exc_info=True)

if __name__ == "__main__":
    main()
