# -*- coding: utf-8 -*-
"""阶段03 辅助：DeepSeek API 直连调用（替代 agent-hub 委派）。

用法：
    $env:DEEPSEEK_API_KEY = "sk-..."
    python -X utf8 清洗/03_化学物质抽取消歧/scripts/call_deepseek.py `
        --prompt 清洗/03_化学物质抽取消歧/prompts/01_化学物质抽取提示词.md `
        --input 清洗/03_化学物质抽取消歧/out/extraction_input/{doc}.jsonl `
        --output 清洗/03_化学物质抽取消歧/out/extraction/{doc}.json

提示词中的 {INPUT} 替换为输入文件路径、{OUTPUT} 替换为输出文件路径；
输入文件内容随请求一并发送；模型回复原样写入输出文件。
仅依赖标准库。
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

API_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("缺少 DEEPSEEK_API_KEY 环境变量。", file=sys.stderr)
        return 1

    input_path = Path(args.input)
    output_path = Path(args.output)
    template = Path(args.prompt).read_text(encoding="utf-8")
    body = template.replace("{INPUT}", str(input_path)) \
                   .replace("{OUTPUT}", str(output_path))
    data = input_path.read_text(encoding="utf-8")
    user = body + "\n\n以下是输入文件内容：\n```jsonl\n" + data + "\n```"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system",
             "content": "你是严谨的文献信息抽取器，只输出要求的 JSON。"},
            {"role": "user", "content": user},
        ],
        "temperature": 0.0,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=args.timeout) as r:
        resp = json.loads(r.read().decode("utf-8"))
    text = resp["choices"][0]["message"]["content"]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(f"written: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())