"""全局配置：所有路径和模型参数集中在这里，改这一处就够了。

新手提示：项目里没有任何"魔法数字"，想换模型、换检索条数，改这里。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------- 路径
# 项目根目录（src 的上一级）
ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data" / "docs"      # 知识库原始文档（Markdown）
STORAGE_DIR = ROOT / "storage"          # 索引、缓存等生成物
CHUNKS_FILE = STORAGE_DIR / "chunks.jsonl"
INDEX_FILE = STORAGE_DIR / "bm25.pkl"


@dataclass
class OllamaConfig:
    """本地 Ollama 服务的连接参数。"""

    host: str = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    model: str = os.getenv("RAG_MODEL", "qwen3-heretic:latest")
    # 生成参数：新手问答不需要太发散，温度调低一点更稳
    temperature: float = 0.3
    top_p: float = 0.9
    num_ctx: int = 8192          # 上下文窗口，8B 在 8G 显存上 8k 比较安全
    num_predict: int = 800       # 单次回答最多生成多少 token
    timeout: int = 600           # 秒，CPU 推理时可能要等很久


@dataclass
class RetrievalConfig:
    """检索参数。"""

    top_k: int = 4               # 最终喂给模型几段资料
    candidate_k: int = 12        # 初筛候选数量（再按分数过滤）
    min_score: float = 0.05      # 低于这个 BM25 分数的片段直接丢掉


@dataclass
class ChunkConfig:
    """切块参数：中文按字符数估算，一个汉字≈1 token 量级。"""

    max_chars: int = 500         # 单块最大字符数
    overlap_chars: int = 80      # 相邻块重叠，避免答案被切断


@dataclass
class Settings:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    chunk: ChunkConfig = field(default_factory=ChunkConfig)


settings = Settings()

# 让 storage 目录始终存在
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
