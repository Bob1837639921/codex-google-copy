---
name: nodex-browser-agent
description: 使用本地 NodeX Browser Agent Chrome 自动化桥，通过 server_live.py 和 agent_core.py 控制已安装的 Chrome 扩展，支持导航、DOM 快照、点击、输入、悬停、JS 执行，以及通过 smart_save() 智能路由将任意 URL 资源写入本地，自动在图片直存（fetch_as_file）和 Blob 回退下载（download_via_blob）之间切换，完全绕过 FDM 等第三方下载管理器拦截。
---

# NodeX Browser Agent

当用户需要通过本仓库的本地桥接控制 Chrome 时，使用此技能。

如果已安装插件的 MCP Server，优先使用 `nodex_*` 工具，无需另写脚本。

## 环境要求

- `extension/` 目录中的 Chrome 扩展必须以开发者模式加载（加载后需刷新才能生效新 background.js）。
- 在仓库根目录启动桥接服务：

```bash
python server_live.py
```

- 安装 Python 依赖：

```bash
pip install -r requirements.txt
```

## SDK 方法一览

所有方法均挂载在 `agent_core.BrowserAgent` 上：

| 方法 | 说明 |
|------|------|
| `connect()` | 建立 WebSocket 连接（max_size=50MB）|
| `init(task_name)` | 附着到或创建受控 Chrome 标签组 |
| `navigate(url)` | 导航受控标签到指定 URL |
| `snapshot()` | 获取 DOM 快照和登录墙检测结果 |
| `hover(selector)` | 将虚拟光标移动到 CSS 选择器 |
| `click(selector)` | 点击 CSS 选择器对应元素 |
| `type(selector, text)` | 向输入元素输入文本 |
| `evaluate(js_code)` | 在受控页面执行 JavaScript 并返回结果 |
| `download(url, filename)` | chrome.downloads API 原生下载（可能被 FDM 拦截，慎用）|
| `search_downloads(query)` | 查询 Chrome 下载历史 |
| `fetch_as_file(url, dest_path)` | 图片专用直存：扩展后台带 Cookie fetch → base64 → 直接写入任意路径 |
| `download_via_blob(url, filename)` | 大文件/非图片：扩展 fetch → blob: URL → chrome.downloads（FDM 不拦截）|
| `smart_save(url, dest_path)` | ⭐ **推荐**：自动路由，图片走直存，其他走 Blob 回退 |
| `close()` | 优雅关闭 WebSocket 连接 |

## 下载方式对比

| 方法 | 后台安全 | 需要窗口唤醒 | FDM 拦截 | 目标路径 |
|------|---------|------------|---------|---------|
| Fetch+Blob（旧方式）| ❌ | ✅ 必须前台 | ❌ 不拦截 | Downloads 文件夹 |
| `download()` | ✅ | ❌ | ⚠️ 可能弹框 | Downloads 文件夹 |
| `fetch_as_file()` | ✅ | ❌ | ✅ 完全绕过 | **任意本地路径** |
| `download_via_blob()` | ✅ | ❌ | ✅ 完全绕过 | Downloads 文件夹 |
| `smart_save()` ⭐ | ✅ | ❌ | ✅ 完全绕过 | 图片→任意路径；其他→Downloads |

## smart_save() 路由逻辑

```
smart_save(url, dest_path)
    │
    ├─ 先尝试 fetch_as_file()
    │       │
    │       ├─ 成功（image/*，< 30MB）→ 直接写入 dest_path ✅
    │       │
    │       ├─ reason = "unsupported_mime" → 回退 download_via_blob()
    │       │       → blob: URL → chrome.downloads → Downloads/filename ✅
    │       │
    │       ├─ reason = "file_too_large"（> 30MB）→ 回退 download_via_blob()
    │       │       → blob: URL → chrome.downloads → Downloads/filename ✅
    │       │
    │       └─ 其他错误 → 返回 error dict
```

## fetch_as_file() 限制说明

- 仅支持 `image/*` MIME 类型（PNG、JPG、WebP、GIF 等）
- 文件大小上限 30MB（Base64 后约 40MB，在 50MB WebSocket 限制内）
- 超出限制时 background.js 返回 `reason: "unsupported_mime"` 或 `"file_too_large"`
- Python 端 `smart_save()` 会自动捕获这两个 reason 并切换到 `download_via_blob()`

## 工作流

1. 在启动新服务前确认 `server_live.py` 是否已在运行。
2. 通过 `agent_core.BrowserAgent` 连接，默认地址 `ws://localhost:8765/client`。
3. 在控制标签前先调用 `await agent.init("任务名称")`。
4. 在购物、登录、支付或验证类页面点击/输入前，先调用 `await agent.snapshot()`。
5. 若 `snapshot()["blocked_by_login"]` 为 True，立刻停止并通知用户手动处理。
6. **下载文件统一使用 `smart_save(url, dest_path)`**，无需手动判断文件类型。

## 安全注意事项

- 扩展拥有广泛的 Chrome 调试器访问权限，只应连接到本地桥接。
- 不执行不受信任的动作计划或任意 JavaScript。
- 不绕过 CAPTCHA、滑块验证、登录墙、支付确认或账号安全提示。
- 与已认证网站交互时，保持自动化可见并由用户监督。

## 最简示例

```python
import asyncio
from agent_core import BrowserAgent

async def main():
    agent = BrowserAgent()
    await agent.connect()
    await agent.init("Codex 浏览器任务")
    await agent.navigate("https://www.google.com")
    snapshot = await agent.snapshot()
    if snapshot["blocked_by_login"]:
        return
    await agent.close()

asyncio.run(main())
```

## 图片生成直存管线示例

```python
import asyncio, os
from agent_core import BrowserAgent

CHATGPT_URL = "https://chatgpt.com/c/<你的会话ID>"
DEST_PATH   = "C:/Ai/character/白无垢/05-服装差分/cover.png"

async def main():
    agent = BrowserAgent()
    await agent.connect()
    await agent.init("图片生成管线")
    await agent.navigate(CHATGPT_URL)
    await asyncio.sleep(6.0)

    # 1. 记录当前已有的 DALL-E 图片 URL
    scan_js = """
    (() => {
        return Array.from(document.querySelectorAll('img'))
            .map(i => i.src)
            .filter(s => s && (s.includes('oaiusercontent.com') || s.includes('estuary/content'))
                      && !s.includes('profile'));
    })()
    """
    pre_srcs = set(await agent.evaluate(scan_js) or [])

    # 2. 发送生成 prompt
    await agent.type("#prompt-textarea", "绘制人物服装差分，超高精度，8k。")
    await asyncio.sleep(1.5)
    await agent.evaluate("""
        (() => {
            const btn = document.querySelector('button[data-testid="send-button"]');
            if (btn) btn.click();
        })()
    """)

    # 3. 轮询等待新图片（最多 225 秒）
    new_url = None
    for _ in range(45):
        await asyncio.sleep(5.0)
        srcs = await agent.evaluate(scan_js) or []
        new = [s for s in srcs if s not in pre_srcs]
        if new:
            new_url = new[-1]
            break

    if not new_url:
        print("超时未检测到新图片。")
        await agent.close()
        return

    # 4. 智能保存：图片自动走 fetch_as_file()，直接写入目标路径
    #    如果是非图片/大文件，自动回退到 download_via_blob()
    result = await agent.smart_save(new_url, DEST_PATH)
    print(result)
    # 图片成功示例：{'status': 'success', 'path': '...', 'size': 2663442, 'mime': 'image/png'}
    # 大文件回退示例：{'status': 'success', 'downloadId': 96, 'mime': 'video/mp4'}

    await agent.close()

asyncio.run(main())
```
