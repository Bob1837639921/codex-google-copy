import sys
import os
import json
import re
import argparse
import subprocess
import logging

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

ROOT = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(ROOT, "skills", "skills_registry.json")

def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        raise FileNotFoundError(f"Registry config not found at: {REGISTRY_PATH}")
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_search_keyword(query: str, triggers: list[str]) -> str:
    """
    Extracts the subject search keyword from the query, removing the triggers and verb prefixes.
    For example: "在淘宝上搜索显卡" -> "显卡"
    """
    cleaned = query.strip()
    # Remove trigger words
    for trigger in triggers:
        cleaned = re.sub(re.escape(trigger), "", cleaned, flags=re.IGNORECASE)
    
    # Remove common filler verbs and particles
    prefixes = [
        r"^[在去由到里中上用帮我我要给来]*",
        r"^(?:搜索|查找|比价|买个|买东西|寻找|生图|生成|画个|画一下|看看|找一下|搜一下|搜|找|画|买|关于|找个|搜个|画个|生个|制作个|制作|设计个|设计)",
        r"^[一个张只件部支本辆首款只]加?的?",
        r"^[在去由到里中上用帮我我要给来]*"
    ]
    
    for _ in range(3):
        for pattern in prefixes:
            cleaned = re.sub(pattern, "", cleaned).strip()
            
    suffixes = [
        r"[下个一的内容些的好用之类的吧啦啊哈]*$"
    ]
    for pattern in suffixes:
        cleaned = re.sub(pattern, "", cleaned).strip()
    
    # Strip symbols
    cleaned = cleaned.strip(" ？！.,，。!\"'“‘’+-*/")
    return cleaned if cleaned else query

def route_query(query: str) -> dict | None:
    registry = load_registry()
    query_lower = query.lower()
    
    matched_skill = None
    matched_trigger = None
    
    # Find matching skill based on triggers
    for skill in registry.get("skills", []):
        for trigger in skill.get("triggers", []):
            if trigger.lower() in query_lower:
                matched_skill = skill
                matched_trigger = trigger
                break
        if matched_skill:
            break
            
    if not matched_skill:
        return None
        
    extracted_param = extract_search_keyword(query, matched_skill["triggers"])
    
    return {
        "skill": matched_skill,
        "trigger": matched_trigger,
        "extracted_param": extracted_param
    }

def execute_skill(match_result: dict, dry_run: bool = False):
    skill = match_result["skill"]
    param = match_result["extracted_param"]
    
    logging.info(f"✨ 匹配到技能: [{skill['display_name']}] (触发词: '{match_result['trigger']}')")
    logging.info(f"🔎 提取关键参数: '{param}'")
    
    cmd = [sys.executable]
    
    if skill["action_type"] == "auto_operate":
        # Run generic auto operator
        script_path = os.path.join(ROOT, "auto_operator.py")
        goal = f"在{skill['display_name']}搜索 {param}"
        cmd.extend([
            script_path,
            "--goal", goal,
            "--url", skill["url"]
        ])
    elif skill["action_type"] == "script":
        # Run custom script
        script_path = os.path.join(ROOT, skill["script"])
        cmd.append(script_path)
        # If it's character generator, map parameters
        if skill["name"] == "character_generator":
            # Guessing if parameter is a character name or category
            if param:
                cmd.extend(["--char-id", param])
    else:
        logging.error(f"未知的动作类型: {skill['action_type']}")
        return {"status": "error", "error": f"Unknown action type: {skill['action_type']}"}
        
    logging.info(f"🚀 执行命令: {' '.join(cmd)}")
    
    if dry_run:
        logging.info("[干跑模式] 跳过子进程执行。")
        return {"status": "dry_run", "command": cmd}
        
    try:
        # Run command synchronously and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='ignore',
            bufsize=1
        )
        
        output_lines = []
        while True:
            line = process.stdout.readline()
            if not line:
                break
            line_str = line.strip()
            if line_str:
                logging.info(f"[Runner] {line_str}")
                output_lines.append(line_str)
                
        process.wait()
        
        if process.returncode == 0:
            logging.info("🎉 子任务执行成功！")
            return {"status": "success", "returncode": 0, "output": output_lines}
        else:
            logging.error(f"❌ 子任务执行失败，退出代码: {process.returncode}")
            return {"status": "failed", "returncode": process.returncode, "output": output_lines}
            
    except Exception as e:
        logging.error(f"执行子程序发生异常: {e}")
        return {"status": "error", "error": str(e)}

def main():
    parser = argparse.ArgumentParser(description="NodeX 智能技能触发路由器")
    parser.add_argument("--query", required=True, help="用户自然语言查询指令")
    parser.add_argument("--dry-run", action="store_true", help="仅分析并打印命令，不实际运行")
    args = parser.parse_args()
    
    match = route_query(args.query)
    if not match:
        logging.warning("⚠️ 没有匹配到任何已注册的技能触发词。")
        print(json.dumps({"status": "no_match", "query": args.query}))
        return
        
    result = execute_skill(match, dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
