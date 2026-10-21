"""文档切块：把 data/docs/*.md 切成一段段小文本（chunk）。

为什么要切块？
    模型一次能读的上下文有限，而且把整篇文档塞进去既慢又容易"看丢"重点。
    切成 500 字左右的小块，检索时只挑最相关的几块，答案才准。

切块策略（对新手最友好的一种）：
    1. 先按 Markdown 标题(#/##/###)切开，保证每条切块语义完整；
    2. 如果某个小节还是太长，再按段落/句子二次切分，并保留少量重叠；
    3. 每块都记住自己来自哪个文件、哪一级标题，方便回答时标注出处。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .config import CHUNKS_FILE, DATA_DIR, settings

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


@dataclass
class Chunk:
    """一条可检索的文本片段。"""

    chunk_id: str      # 唯一 id，例如 "01-第一天生存清单.md#2-0"
    doc_title: str     # 文档大标题
    heading: str       # 所在小节标题
    text: str          # 正文
    source: str        # 相对 data/docs 的文件名

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def _iter_sections(md_text: str) -> Iterable[tuple[str, str, str]]:
    """把文档拆成 (文档标题, 小节标题, 小节正文) 的序列。"""
    doc_title = ""
    heading = ""
    buf: list[str] = []

    def flush() -> tuple[str, str, str] | None:
        body = "\n".join(buf).strip()
        if not body:
            return None
        return doc_title, heading, body

    for raw in md_text.splitlines():
        line = raw.rstrip()
        m = HEADING_RE.match(line)
        if m:
            level, title = len(m.group(1)), m.group(2).strip()
            done = flush()
            if done:
                yield done
            buf = []
            if level == 1:
                doc_title = title
                heading = title
            else:
                heading = title
            continue
        buf.append(line)

    done = flush()
    if done:
        yield done


def _split_long(text: str, max_chars: int, overlap: int) -> list[str]:
    """把过长的正文按句子边界切成多段，段间保留 overlap 个字符的重叠。"""
    if len(text) <= max_chars:
        return [text]

    sentences: list[str] = []
    for seg in SENTENCE_SPLIT_RE.split(text):
        if seg.strip():
            sentences.append(seg.strip())

    pieces: list[str] = []
    cur = ""
    for sent in sentences:
        # 单句本身就超长（比如表格行、长列表），先硬切
        while len(sent) > max_chars:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(sent[:max_chars])
            sent = sent[max_chars:]
        if len(cur) + len(sent) + 1 <= max_chars:
            cur = f"{cur}{sent}" if cur else sent
        else:
            if cur:
                pieces.append(cur)
                tail = cur[-overlap:] if overlap and len(cur) > overlap else cur
                cur = f"{tail}{sent}"
            else:
                cur = sent
    if cur:
        pieces.append(cur)

    # 重叠拼接后再兜底一次长度限制
    return [p for p in pieces if p.strip()]


def build_chunks(data_dir: Path = DATA_DIR) -> list[Chunk]:
    """扫描目录下所有 .md，产出全部 Chunk。"""
    cfg = settings.chunk
    files = sorted(data_dir.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"没有找到任何 .md 文档：{data_dir}")

    chunks: list[Chunk] = []
    for path in files:
        rel = path.name
        md = path.read_text(encoding="utf-8")
        per_doc_index = 0
        for doc_title, heading, body in _iter_sections(md):
            for piece in _split_long(body, cfg.max_chars, cfg.overlap_chars):
                # 给切块补上小节标题，避免脱离上下文后看不懂"它"指什么
                prefix = f"【{doc_title} · {heading}】" if heading and heading != doc_title else f"【{doc_title}】"
                text = f"{prefix}\n{piece}".strip()
                chunks.append(
                    Chunk(
                        chunk_id=f"{path.stem}#{per_doc_index}",
                        doc_title=doc_title or path.stem,
                        heading=heading,
                        text=text,
                        source=rel,
                    )
                )
                per_doc_index += 1
    return chunks


def save_chunks(chunks: list[Chunk], out: Path = CHUNKS_FILE) -> Path:
    """把切块写成 JSONL，方便你直接打开检查切得好不好。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(c.to_json() + "\n")
    return out


def load_chunks(path: Path = CHUNKS_FILE) -> list[Chunk]:
    if not path.exists():
        raise FileNotFoundError(f"{path} 不存在，先运行：python -m src.cli build")
    out: list[Chunk] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(Chunk(**json.loads(line)))
    return out


def main() -> None:
    chunks = build_chunks()
    path = save_chunks(chunks)
    print(f"✅ 切块完成：{len(chunks)} 块 -> {path}")
    longest = max(chunks, key=lambda c: len(c.text))
    print(f"   最长块 {len(longest.text)} 字（{longest.chunk_id}）")


if __name__ == "__main__":
    main()
