import asyncio
import websockets
import json
import uuid
import os
import sys
import concurrent.futures

sys.stdout.reconfigure(encoding='utf-8')

connected_client = None
responses = {}

connected_extension = None
connected_clients = {}  # cmd_id -> client_websocket
responses = {}

async def handler(websocket, path=None):
    global connected_extension
    # Auto-detect path for routing (extension on root /, clients on /client)
    req_path = "/"
    if hasattr(websocket, "request") and hasattr(websocket.request, "path"):
        req_path = websocket.request.path
    elif path:
        req_path = path
    
    if "client" in req_path:
        print("[Server] Python controller client connected!")
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    cmd_id = data.get("id")
                    if cmd_id:
                        if connected_extension:
                            # Map this command ID to the active client connection
                            connected_clients[cmd_id] = websocket
                            # Forward directly to the Chrome extension
                            await connected_extension.send(message)
                        else:
                            await websocket.send(json.dumps({
                                "id": cmd_id, 
                                "status": "error", 
                                "error": "Browser extension not connected"
                            }, ensure_ascii=False))
                except Exception as ex:
                    print(f"Error forwarding client message: {ex}")
        except websockets.exceptions.ConnectionClosed:
            print("[Server] Python controller client disconnected.")
    else:
        print("[Server] Browser extension connected!")
        connected_extension = websocket
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    cmd_id = data.get("id")
                    if cmd_id:
                        # If this belongs to an external client, dispatch it back
                        if cmd_id in connected_clients:
                            client_ws = connected_clients.pop(cmd_id)
                            try:
                                await client_ws.send(message)
                            except:
                                pass
                        else:
                            # Otherwise fall back to stdout/stdin responses
                            responses[cmd_id] = data
                except Exception as ex:
                    print(f"Error processing extension message: {ex}")
        except websockets.exceptions.ConnectionClosed:
            print("[Server] Browser extension disconnected.")
        finally:
            connected_extension = None

async def send_command(action, **kwargs):
    global connected_extension
    if not connected_extension:
        # 等待连接
        for _ in range(30):
            if connected_extension:
                break
            await asyncio.sleep(0.5)
        if not connected_extension:
            return {"status": "error", "error": "Browser extension not connected"}
            
    cmd_id = str(uuid.uuid4())
    cmd = {"id": cmd_id, "action": action}
    cmd.update(kwargs)
    
    await connected_extension.send(json.dumps(cmd))
    
    # 阻塞等待响应
    for _ in range(150): # 最多等 30 秒
        if cmd_id in responses:
            return responses.pop(cmd_id)
        await asyncio.sleep(0.2)
    return {"status": "timeout"}

def blocking_input():
    return sys.stdin.readline()

async def stdin_loop():
    print("[LiveBridge] Ready for stdin commands! Format: {\"action\": \"...\"}")
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        while True:
            # 在独立线程中阻塞读取标准输入，防止阻塞 asyncio 事件循环
            line = await loop.run_in_executor(pool, blocking_input)
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                cmd_data = json.loads(line)
                action = cmd_data.pop("action")
                # 瞬间通过长连接发送给插件并等待响应
                res = await send_command(action, **cmd_data)
                # 瞬间把响应打印在控制台
                print(json.dumps(res, ensure_ascii=False), flush=True)
            except Exception as e:
                print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False), flush=True)

async def main():
    print("Starting Live Bridge server on port 8765...")
    try:
        server = await websockets.serve(handler, "localhost", 8765)
        # 启动常驻标准输入监听循环
        asyncio.create_task(stdin_loop())
        await server.wait_closed()
    except Exception as e:
        print(f"Server error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
