"""RAG 主流程：问题 -> 检索 -> 拼上下文 -> 让本地模型作答 -> 返回答案和出处。"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import llm
from .config import settings
from .prompt import build_messages
from .retrieve import BM25Index, Hit, rerank_semantic


@dataclass
class Answer:
    question: str
    text: str
    sources: list[Hit] = field(default_factory=list)
    thinking: str = ""

    def cite_lines(self) -> list[str]:
        """生成末尾的"参考来源"清单。"""
        lines = []
        for i, hit in enumerate(self.sources, start=1):
            c = hit.chunk
            lines.append(f"[{i}] {c.source} · {c.heading}（相关度 {hit.rel:.2f}）")
        return lines


class RagEngine:
    def __init__(self, index: BM25Index | None = None) -> None:
        self.index = index or BM25Index.load()

    def retrieve(self, question: str, top_k: int | None = None, hybrid: bool = False) -> list[Hit]:
        cfg = settings.retrieval
        k = top_k or cfg.top_k
        hits = self.index.search(question, top_k=k)
        if hybrid and hits:
            hits = rerank_semantic(question, hits, top_k=k)
        return hits

    def ask(self, question: str, top_k: int | None = None, hybrid: bool = False, think: bool = False) -> Answer:
        """一次性拿到完整答案。"""
        hits = self.retrieve(question, top_k=top_k, hybrid=hybrid)
        messages = build_messages(question, hits)
        text, thinking = llm.chat(messages, think=think)
        return Answer(question=question, text=text, sources=hits, thinking=thinking)

    def ask_stream(self, question: str, top_k: int | None = None, hybrid: bool = False, think: bool = False) -> tuple[list[Hit], "object"]:
        """流式问答：先返回检索结果，再返回一个逐段产出文本的生成器。"""
        hits = self.retrieve(question, top_k=top_k, hybrid=hybrid)
        messages = build_messages(question, hits)
        return hits, llm.chat_stream(messages, think=think)
