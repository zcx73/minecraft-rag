"""命令行入口。

常用：
    python -m src.cli build                 # 切块 + 建索引（改了 data/docs 后重跑）
    python -m src.cli ask "钻石在哪挖"       # 问一个问题
    python -m src.cli chat                  # 进入连续对话模式
    python -m src.cli doctor                # 自检：依赖 / 索引 / 模型
"""

from __future__ import annotations

import argparse
import sys
import time

from . import llm
from .config import CHUNKS_FILE, INDEX_FILE, DATA_DIR, settings
from .ingest import build_chunks, save_chunks
from .rag import RagEngine
from .retrieve import BM25Index


def _init_console() -> None:
    """Windows 终端默认 GBK，中文会乱码，这里强制 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def cmd_build(_: argparse.Namespace) -> int:
    chunks = build_chunks()
    save_chunks(chunks)
    BM25Index(chunks).save()
    sizes = [len(c.text) for c in chunks]
    print(f"✅ 知识库就绪")
    print(f"   文档：{len(list(DATA_DIR.glob('*.md')))} 篇 | 切块：{len(chunks)} 块")
    print(f"   切块长度：平均 {sum(sizes)//len(sizes)} 字，最长 {max(sizes)} 字")
    print(f"   产物：{CHUNKS_FILE.name} / {INDEX_FILE.name}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    engine = RagEngine()
    t0 = time.time()
    hits = engine.retrieve(args.question, top_k=args.top_k, hybrid=args.hybrid)
    if not hits:
        print("⚠️  没有检索到相关资料，模型只会凭自身知识回答。\n")

    hits, stream = engine.ask_stream(args.question, top_k=args.top_k, hybrid=args.hybrid, think=args.think)
    if not args.quiet:
        print("🔍 检索到的资料：")
        for i, h in enumerate(hits, start=1):
            print(f"   [{i}] {h.chunk.source} · {h.chunk.heading}（{h.rel:.2f}）")
        print()

    print("💬 回答：")
    first_token_at = None
    for piece in stream:
        if first_token_at is None:
            first_token_at = time.time()
        sys.stdout.write(piece)
        sys.stdout.flush()
    print()

    if not args.quiet:
        print("\n📚 来源：")
        for i, h in enumerate(hits, start=1):
            print(f"   [{i}] {h.chunk.source} · {h.chunk.heading}")

    first = (first_token_at or time.time()) - t0
    print(f"\n⏱  首字 {first:.1f}s，总耗时 {time.time() - t0:.1f}s")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    engine = RagEngine()
    print("💬 进入问答模式，输入 exit 退出。")
    while True:
        try:
            question = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见 👋")
            return 0
        if not question:
            continue
        if question.lower() in {"exit", "quit", "q"}:
            print("再见 👋")
            return 0
        hits, stream = engine.ask_stream(question, top_k=args.top_k, hybrid=args.hybrid, think=args.think)
        print("助手> ", end="", flush=True)
        for piece in stream:
            sys.stdout.write(piece)
            sys.stdout.flush()
        print()
        if hits:
            used = "、".join(f"[{i}]{h.chunk.heading}" for i, h in enumerate(hits, start=1))
            print(f"（依据：{used}）")


def cmd_doctor(_: argparse.Namespace) -> int:
    print("== 环境自检 ==")
    ok = True

    import jieba  # noqa: F401
    import numpy  # noqa: F401
    import rank_bm25  # noqa: F401
    import requests  # noqa: F401

    print(f"✅ Python {sys.version.split()[0]}")
    print("✅ 依赖齐全：jieba / rank_bm25 / numpy / requests")

    if CHUNKS_FILE.exists() and INDEX_FILE.exists():
        idx = BM25Index.load()
        print(f"✅ 索引就绪：{len(idx.chunks)} 块")
    else:
        ok = False
        print("❌ 还没有索引，请先运行：python -m src.cli build")

    healthy, msg = llm.health()
    print(("✅ " if healthy else "❌ ") + msg)
    ok = ok and healthy
    print(f"   模型参数：temperature={settings.ollama.temperature}, num_ctx={settings.ollama.num_ctx}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Minecraft 新手 RAG（本地 Ollama）")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("build", help="切块并构建检索索引").set_defaults(func=cmd_build)

    ask = sub.add_parser("ask", help="问一个问题")
    ask.add_argument("question", help="你的问题")
    ask.add_argument("--top-k", type=int, default=None, help="使用几段资料，默认取配置值")
    ask.add_argument("--hybrid", action="store_true", help="额外用向量语义重排（较慢）")
    ask.add_argument("--think", action="store_true", help="显示模型的思考过程")
    ask.add_argument("--quiet", action="store_true", help="只输出回答，不打印检索和来源")
    ask.set_defaults(func=cmd_ask)

    chat = sub.add_parser("chat", help="连续对话模式")
    chat.add_argument("--top-k", type=int, default=None)
    chat.add_argument("--hybrid", action="store_true")
    chat.add_argument("--think", action="store_true")
    chat.set_defaults(func=cmd_chat)

    sub.add_parser("doctor", help="检查依赖、索引和模型").set_defaults(func=cmd_doctor)
    return p


def main(argv: list[str] | None = None) -> int:
    _init_console()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        return 1
    except KeyboardInterrupt:
        print("\n已中断")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
