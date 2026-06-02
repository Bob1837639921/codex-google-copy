---
name: nodex-browser-agent
description: 使用本地 NodeX Browser Agent Chrome 自动化桥，通过 server_live.py 和 agent_core.py 控制已安装的 Chrome 扩展，支持导航、DOM 快照、点击、输入、悬停、页面 JS 执行，以及通过扩展上下文直接将任意 URL 资源（如 ChatGPT DALL-E 图片）写入本地任意路径（无需 chrome.downloads，不触发第三方下载管理器）。
---

# NodeX Browser Agent

当用户需要通过本仓库的本地桥接控制 Chrome 时，使用此技能。

如果已安装插件的 MCP Server，优先使用 `nodex_*` 工具，无需另写脚本。

## 环境要求

- `extension/` 目录中的 Chrome 扩展必须以开发者模式加载。
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
| `connect()` | 建立 WebSocket 连接到桥接服务 |
| `init(task_name)` | 附着到或创建受控 Chrome 标签组 |
| `navigate(url)` | 导航受控标签到指定 URL |
| `snapshot()` | 获取 DOM 快照和登录墙检测结果 |
| `hover(selector)` | 将虚拟光标移动到 CSS 选择器 |
| `click(selector)` | 点击 CSS 选择器对应元素 |
| `type(selector, text)` | 向输入元素输入文本 |
| `evaluate(js_code)` | 在受控页面执行 JavaScript 并返回结果 |
| `download(url, filename)` | 通过 `chrome.downloads.download` API 下载文件（注意：可能被 FDM 等第三方下载管理器拦截） |
| `search_downloads(query)` | 通过 `chrome.downloads.search` 查询 Chrome 下载历史 |
| `fetch_as_file(url, dest_path)` | **推荐**：扩展后台用认证 Cookie 直接 fetch URL，base64 传给 Python 后写入指定路径，完全绕过 chrome.downloads，不触发任何下载管理器 |
| `close()` | 优雅关闭 WebSocket 连接 |

## MCP 工具

插件通过 `scripts/nodex_mcp_server.py` 暴露以下工具：

- `nodex_status`：检查本地桥接和扩展连通性。
- `nodex_init`：创建或附着受控 Chrome 标签组。
- `nodex_navigate`：导航受控标签到 URL。
- `nodex_snapshot`：检查可见 DOM 元素和登录墙状态。
- `nodex_hover`：移动虚拟光标到选择器。
- `nodex_click`：安全快照检查后点击选择器。
- `nodex_type`：安全快照检查后输入文本。
- `nodex_evaluate`：在受控标签中运行可信 JavaScript。
- `nodex_download`：触发后台安全的 URL 下载（可能被 FDM 拦截）。
- `nodex_search_downloads`：查询最近下载历史。
- `nodex_run_action_plan`：执行顺序 JSON 动作计划。

## 标准工作流

1. 在启动新服务前确认 `server_live.py` 是否已在运行。
2. 通过 `agent_core.BrowserAgent` 连接，默认地址 `ws://localhost:8765/client`。
3. 在控制标签前先调用 `await agent.init("任务名称")`。
4. 在购物、登录、支付或验证类页面点击/输入前，调用 `await agent.snapshot()`。
5. 若 `snapshot()["blocked_by_login"]` 为 True，立刻停止自动化并通知用户手动处理。
6. **下载文件时，优先使用 `await agent.fetch_as_file(url, dest_path)`** — 后台安全，直接写入任意本地路径，不需要 Downloads 文件夹中转，不触发 FDM 等第三方下载管理器。

## 下载方式对比

| 方式 | 后台安全 | 需要窗口唤醒 | FDM 拦截 | 需要中转文件夹 |
|------|---------|------------|---------|-------------|
| Fetch+Blob (`a.click()`) | ❌ | ✅ 必须前台 | ❌ 不拦截 | ✅ 需要 |
| `chrome.downloads.download` | ✅ | ❌ | ⚠️ 可能拦截弹框 | ✅ 需要 |
| `fetch_as_file()` ⭐ | ✅ | ❌ | ✅ 完全绕过 | ❌ 直接写目标路径 |

## 安全注意事项

- 扩展拥有广泛的 Chrome 调试器访问权限，只应连接到本地桥接。
- 不执行不受信任的动作计划或任意 JavaScript。
- 不绕过 CAPTCHA、滑块验证、登录墙、支付确认或账号安全提示。
- 与已认证的网站交互时，保持自动化可见并由用户监督。

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

## 图片生成与直存管线示例

使用 `fetch_as_file()` 在 ChatGPT 上生成图片后**直接写入任意本地路径**，无需 Downloads 文件夹，不触发 FDM：

```python
import asyncio, os, time, json
from agent_core import BrowserAgent

CHATGPT_URL = "https://chatgpt.com/c/<你的会话ID>"
DEST_PATH   = "C:/Ai/character/白无垢/05-服装差分/cover.png"

async def main():
    agent = BrowserAgent()
    await agent.connect()
    await agent.init("图片生成管线")
    await agent.navigate(CHATGPT_URL)
    await asyncio.sleep(6.0)          # 等待页面完全加载

    # 1. 记录当前已有的 DALL-E 图片 URL（用于后续对比新增）
    scan_js = """
    (() => {
        const imgs = Array.from(document.querySelectorAll('img'));
        return imgs.map(i => i.src).filter(s =>
            s && (s.includes('oaiusercontent.com') || s.includes('estuary/content'))
            && !s.includes('profile')
        );
    })()
    """
    pre_srcs = set(await agent.evaluate(scan_js) or [])

    # 2. 输入 prompt 并发送
    await agent.type("#prompt-textarea", "绘制一张人物肖像，超高精度，8k。")
    await asyncio.sleep(1.5)
    await agent.evaluate("""
        (() => {
            const btn = document.querySelector('button[data-testid="send-button"]');
            if (btn) btn.click();
        })()
    """)

    # 3. 轮询等待新图片出现（最多 225 秒）
    new_url = None
    for _ in range(45):
        await asyncio.sleep(5.0)
        current = await agent.evaluate(scan_js) or []
        new = [s for s in current if s not in pre_srcs]
        if new:
            new_url = new[-1]
            break

    if not new_url:
        print("未检测到新图片，退出。")
        await agent.close()
        return

    # 4. 通过扩展上下文直接获取图片并写入目标路径
    #    - 后台安全，无需窗口处于激活状态
    #    - 完全绕过 chrome.downloads，FDM 不会弹框
    #    - 直接写入任意本地路径，无需 Downloads 文件夹中转
    result = await agent.fetch_as_file(new_url, DEST_PATH)
    print("结果:", result)
    # 输出示例：{'status': 'success', 'path': '...', 'size': 2663442, 'mime': 'image/png'}

    if result["status"] == "success":
        print(f"成功！{result['size'] / 1024:.1f} KB 已保存至：{result['path']}")
    
    await agent.close()

asyncio.run(main())
```
