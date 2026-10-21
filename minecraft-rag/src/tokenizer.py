"""中文分词（带兜底方案）。

优先用 jieba：分词准确，"下界合金""附魔台"这类专有名词能整体切出来。
如果环境里没有 jieba（比如离线装不上），自动退化成"单字 + 二元组"切分，
BM25 对中文的检索效果依然可用，项目不会因为少一个包就跑不起来。
"""

from __future__ import annotations

import re

try:  # pragma: no cover - 取决于环境
    import jieba

    # jieba 默认会往 stderr 打印"Building prefix dict..."，会干扰 CLI 输出
    import logging as _logging

    jieba.setLogLevel(_logging.ERROR)

    # 把游戏里的专有名词加进词典，避免被切成零碎的字（否则"苦力怕"会变成"苦力"+"怕"）
    GAME_TERMS = (
        "苦力怕", "爬行者", "末影人", "末影珍珠", "末影之眼", "末地城", "末地船",
        "下界合金", "下界合金锭", "远古残骸", "下界要塞", "烈焰人", "烈焰棒",
        "附魔台", "附魔书", "经验修补", "精准采集", "红石中继器", "红石比较器",
        "粘性活塞", "潜影盒", "潜影贝", "鞘翅", "铁傀儡", "流浪商人", "掠夺者",
        "村庄英雄", "不祥之兆", "刷怪笼", "熔炉", "高炉", "锻造台", "切石机",
    )
    for _term in GAME_TERMS:
        jieba.add_word(_term, freq=10000)

    HAS_JIEBA = True
except Exception:  # noqa: BLE001
    jieba = None  # type: ignore[assignment]
    HAS_JIEBA = False

# 停用词：中文里高频但几乎不携带检索信息的词
STOPWORDS = set(
    "的 了 是 在 我 你 他 她 它 们 吗 呢 吧 啊 和 与 或 就 都 也 还 要 会 能 可以 "
    "怎么 如何 什么 哪些 哪个 为什么 一下 一个 这个 那个 请 帮 我想 知道 请问 有 没有 一些".split()
)

# 同义词扩展：玩家口语和官方译名经常对不上，查的时候两边都带上
SYNONYMS: dict[str, tuple[str, ...]] = {
    "苦力怕": ("爬行者", "creeper"),
    "爬行者": ("苦力怕",),
    "末影人": ("安德", "enderman"),
    "末影龙": ("enderdragon",),
    "钻石": ("diamond",),
    "附魔": ("enchant",),
    "饥饿": ("food", "吃饭"),
    "刷怪": ("生成", "spawn"),
    "经验修补": ("mending",),
    "时运": ("fortune",),
    "精准采集": ("silk", "touch"),
    "下界合金": ("netherite",),
    "下界": ("nether",),
    "末地": ("end",),
    "铁傀儡": ("irongolem",),
}

_LATIN_RE = re.compile(r"[a-zA-Z0-9_.+-]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_PUNCT_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _cjk_fallback(text: str) -> list[str]:
    """没有 jieba 时的兜底：连续汉字切成单字 + 相邻二元组。"""
    out: list[str] = []
    for block in _CJK_RE.findall(text):
        out.extend(block)                       # 单字
        out.extend(block[i : i + 2] for i in range(len(block) - 1))  # 二元组
    return out


def tokenize(text: str) -> list[str]:
    """把一句话切成检索用的词元列表。"""
    if not text:
        return []
    lowered = text.lower()

    tokens: list[str] = []
    if HAS_JIEBA:
        tokens = [t.strip() for t in jieba.lcut(lowered) if t.strip()]
        # jieba 会把连续汉字之外的东西也切出来，这里补上英文/数字
    else:
        tokens = _LATIN_RE.findall(lowered) + _cjk_fallback(lowered)

    result: list[str] = []
    for tok in tokens:
        if tok in STOPWORDS:
            continue
        if _PUNCT_RE.fullmatch(tok):
            continue
        if len(tok) == 1 and not tok.isdigit() and not _CJK_RE.match(tok):
            continue
        result.append(tok)
    return result


def expand_query_tokens(tokens: list[str], raw_query: str = "") -> list[str]:
    """给查询词加上同义词，提升召回（只用于查询，不用于建索引）。

    有些词 jieba 会拆开（"苦力怕"可能被切成"苦力"+"怕"），所以除了逐个词查表，
    还要在整句原文里做一次子串匹配。
    """
    out = list(tokens)
    for term, syns in SYNONYMS.items():
        if term in raw_query or term in out:
            for syn in syns:
                if syn not in out:
                    out.append(syn)
    return out
