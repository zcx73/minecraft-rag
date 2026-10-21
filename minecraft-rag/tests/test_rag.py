"""离线测试：不依赖 Ollama，只验证切块、分词、检索、上下文拼装。

运行：
    .venv\\Scripts\\python -m pytest -q
"""

from __future__ import annotations

from src.config import settings
from src.ingest import build_chunks
from src.prompt import build_messages, format_context
from src.retrieve import BM25Index
from src.tokenizer import expand_query_tokens, tokenize


def test_chunks_have_metadata():
    chunks = build_chunks()
    assert len(chunks) > 20, "知识库切块数量太少，检查 data/docs 是否完整"
    for c in chunks:
        assert c.source.endswith(".md")
        assert c.doc_title, "切块必须带文档标题"
        assert c.text.strip()
        # 允许前缀标题带来的少量超出
        assert len(c.text) <= settings.chunk.max_chars + 80


def test_tokenize_chinese():
    tokens = tokenize("钻石在哪个高度挖")
    assert "钻石" in tokens
    assert "高度" in tokens
    # 停用词和单字标点应被过滤
    assert "的" not in tokens


def test_synonym_expansion():
    question = "苦力怕怎么防"
    expanded = expand_query_tokens(tokenize(question), question)
    assert "爬行者" in expanded


def test_retrieval_hits_expected_doc():
    index = BM25Index(build_chunks())
    cases = {
        "钻石在哪个高度挖": "04-挖矿与矿物.md",
        "苦力怕怎么防": "06-怪物与夜晚安全.md",
        "饥饿值怎么恢复": "05-食物与饥饿.md",
        "红石中继器有什么用": "10-红石入门.md",
    }
    for question, expected in cases.items():
        hits = index.search(question, top_k=3)
        assert hits, f"问题没有检索到任何结果：{question}"
        sources = [h.chunk.source for h in hits[:2]]
        assert expected in sources, f"{question} 的前两条应包含 {expected}，实际 {sources}"


def test_context_has_numbered_sources():
    index = BM25Index(build_chunks())
    hits = index.search("第一天晚上怎么办", top_k=3)
    ctx = format_context(hits)
    assert "[1]" in ctx
    messages = build_messages("第一天晚上怎么办", hits)
    assert messages[0]["role"] == "system"
    assert "【资料】" in messages[0]["content"]
    assert messages[1]["role"] == "user"
