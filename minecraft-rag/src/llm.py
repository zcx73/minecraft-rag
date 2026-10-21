"""模型层：和本地 Ollama 通信（不依赖 ollama 的 Python 包，只用 requests）。

为什么不用 openai / ollama 官方 SDK？
    多一层依赖就多一层安装失败的可能。Ollama 的 HTTP 接口很简单，
    直接 requests 调用，哪一步出错都能一眼看明白。
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

import requests

from .config import settings

THINK_RE = re.compile(r"<think(?:ing)?>(.*?)</think(?:ing)?>", re.S | re.I)


def _payload(messages: list[dict[str, str]], stream: bool, think: bool) -> dict:
    cfg = settings.ollama
    return {
        "model": cfg.model,
        "messages": messages,
        "stream": stream,
        "think": think,          # Qwen3 支持关掉思考链，新手问答更快
        "options": {
            "temperature": cfg.temperature,
            "top_p": cfg.top_p,
            "num_ctx": cfg.num_ctx,
            "num_predict": cfg.num_predict,
        },
    }


def split_think(text: str) -> tuple[str, str]:
    """把 <think>...</think> 从回答里剥出来，返回 (正文, 思考过程)。"""
    thinking = "\n".join(m.group(1).strip() for m in THINK_RE.finditer(text))
    return THINK_RE.sub("", text).strip(), thinking.strip()


def health() -> tuple[bool, str]:
    """检查 Ollama 服务是否活着、模型是否已拉取。"""
    cfg = settings.ollama
    try:
        resp = requests.get(f"{cfg.host}/api/tags", timeout=5)
        resp.raise_for_status()
        names = [m["name"] for m in resp.json().get("models", [])]
    except Exception as exc:  # noqa: BLE001
        return False, f"连不上 Ollama（{cfg.host}）：{exc}\n请先运行 ollama serve"

    if cfg.model not in names:
        return False, f"模型 {cfg.model} 不在本地，已有：{', '.join(names) or '（空）'}"
    return True, f"Ollama 正常，使用模型 {cfg.model}"


def chat(messages: list[dict[str, str]], think: bool = False) -> tuple[str, str]:
    """非流式调用，返回 (正文, 思考过程)。"""
    cfg = settings.ollama
    body = _payload(messages, stream=False, think=think)
    resp = requests.post(f"{cfg.host}/api/chat", json=body, timeout=cfg.timeout)
    if resp.status_code == 400 and think:
        # 老版本 Ollama 不认 think 参数，去掉重试一次
        body.pop("think", None)
        resp = requests.post(f"{cfg.host}/api/chat", json=body, timeout=cfg.timeout)
    resp.raise_for_status()
    content = resp.json()["message"]["content"]
    return split_think(content)


def chat_stream(messages: list[dict[str, str]], think: bool = False) -> Iterator[str]:
    """流式调用，边生成边 yield 文本片段（打字机效果）。"""
    cfg = settings.ollama
    body = _payload(messages, stream=True, think=think)
    with requests.post(f"{cfg.host}/api/chat", json=body, stream=True, timeout=cfg.timeout) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = data.get("message") or {}
            piece = msg.get("content") or ""
            if piece:
                yield piece
            if data.get("done"):
                break


if __name__ == "__main__":
    ok, msg = health()
    print(("✅ " if ok else "❌ ") + msg)
