"""检索层：中文分词 + BM25 关键词检索，可选再加一层向量语义重排。

为什么默认用 BM25 而不是向量库？
    1. 零额外依赖、零模型下载，装完就能跑，最适合新手起步；
    2. 中文游戏问答里"下界合金""附魔台"这类专有名词，关键词命中非常准；
    3. 想升级成向量检索，加一个 embed 模型即可（本项目留了接口）。

检索流程：
    用户问题 -> jieba 分词 -> BM25 打分 -> 取前 candidate_k 条
             -> （可选）用 Ollama 的嵌入向量做语义重排
             -> 过滤低分 -> 取 top_k 条作为参考资料
"""

from __future__ import annotations

import math
import pickle
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from .config import INDEX_FILE, settings
from .ingest import Chunk, load_chunks
from .tokenizer import expand_query_tokens, tokenize


@dataclass
class Hit:
    """一条检索结果。"""

    chunk: Chunk
    score: float        # 原始 BM25 分数
    rel: float          # 归一化后的相关度 0~1，方便展示


class BM25Index:
    """把切块做成 BM25 索引，并支持序列化到磁盘。"""

    def __init__(self, chunks: list[Chunk]) -> None:
        if not chunks:
            raise ValueError("索引为空：知识库里没有内容")
        self.chunks = chunks
        self.corpus_tokens = [tokenize(c.text) for c in chunks]
        self.bm25 = BM25Okapi(self.corpus_tokens)

    # ------------------------------------------------------------ 持久化
    def save(self, path: Path = INDEX_FILE) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"chunks": self.chunks, "tokens": self.corpus_tokens}, f)
        return path

    @classmethod
    def load(cls, path: Path = INDEX_FILE) -> "BM25Index":
        if not path.exists():
            raise FileNotFoundError(f"{path} 不存在，先运行：python -m src.cli build")
        with path.open("rb") as f:
            data = pickle.load(f)
        obj = cls.__new__(cls)
        obj.chunks = data["chunks"]
        obj.corpus_tokens = data["tokens"]
        obj.bm25 = BM25Okapi(obj.corpus_tokens)
        return obj

    # ------------------------------------------------------------ 检索
    def search(self, query: str, top_k: int | None = None) -> list[Hit]:
        cfg = settings.retrieval
        top_k = top_k or cfg.top_k
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        q_expanded = expand_query_tokens(q_tokens, query)
        q_set = set(q_expanded)

        scores = list(self.bm25.get_scores(q_expanded))

        # 小技巧：命中"小节标题"的块加权，标题通常最能概括这一段在讲什么
        for i, chunk in enumerate(self.chunks):
            if scores[i] <= 0:
                continue
            heading_tokens = set(tokenize(chunk.heading))
            overlap = len(q_set & heading_tokens)
            if overlap:
                scores[i] *= 1.0 + 0.12 * min(overlap, 3)

        best = max(scores) if scores else 0.0
        if best <= 0:
            return []

        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[: cfg.candidate_k]
        hits: list[Hit] = []
        seen_heading: dict[tuple[str, str], int] = {}   # 同一小节的块最多取 2 个，避免重复
        for i in order:
            raw = float(scores[i])
            if raw <= 0:
                continue
            rel = raw / best
            if rel < cfg.min_score:
                continue
            chunk = self.chunks[i]
            key = (chunk.source, chunk.heading)
            if seen_heading.get(key, 0) >= 2:
                continue
            seen_heading[key] = seen_heading.get(key, 0) + 1
            hits.append(Hit(chunk=chunk, score=raw, rel=rel))
            if len(hits) >= top_k:
                break
        return hits


# ---------------------------------------------------------------- 可选：语义重排
# 用 Ollama 的 /api/embed 给文本算向量。注意：qwen3-heretic 是聊天模型，
# 它的向量只适合粗排，所以这里只用来"重排候选"，不替代 BM25。
def ollama_embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    import requests

    from .config import settings as cfg

    model = model or cfg.ollama.model
    url = f"{cfg.ollama.host}/api/embed"
    resp = requests.post(url, json={"model": model, "input": texts}, timeout=cfg.ollama.timeout)
    resp.raise_for_status()
    return resp.json()["embeddings"]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb + 1e-8)


def rerank_semantic(query: str, hits: list[Hit], top_k: int) -> list[Hit]:
    """用向量相似度给 BM25 候选重排；失败时原样返回（不影响主流程）。"""
    if not hits:
        return hits
    try:
        vecs = ollama_embed([query] + [h.chunk.text for h in hits])
        q_vec, doc_vecs = vecs[0], vecs[1:]
    except Exception as exc:  # noqa: BLE001 - 重排是加分项，失败不该中断问答
        print(f"[warn] 语义重排跳过：{exc}")
        return hits

    for hit, vec in zip(hits, doc_vecs):
        hit.rel = round(0.5 * hit.rel + 0.5 * _cosine(q_vec, vec), 4)
    return sorted(hits, key=lambda h: h.rel, reverse=True)[:top_k]


def build_index() -> BM25Index:
    chunks = load_chunks()
    index = BM25Index(chunks)
    index.save()
    return index


if __name__ == "__main__":
    idx = build_index()
    print(f"✅ 索引构建完成：{len(idx.chunks)} 块 -> {INDEX_FILE}")
