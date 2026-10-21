"""提示词层：把检索到的资料拼成"有据可依"的上下文。

新手要点：RAG 的效果 70% 取决于提示词写得好不好。
这里的提示词做了三件事：
    1. 限定角色：你是 Minecraft 新手向导；
    2. 限定依据：只能根据【资料】回答，资料里没有就说不知道；
    3. 强制引用：每个事实后面标 [编号]，让用户能溯源。
"""

from __future__ import annotations

from .retrieve import Hit

SYSTEM_PROMPT = """你是「Minecraft 新手向导」，专门用通俗、口语化的中文给刚入坑的玩家讲解。

严格遵守以下规则：
1. 只根据下面给出的【资料】作答，不要编造资料里没有的细节（物品名、数值、版本特性尤其不能瞎写）。
2. 如果资料不足以回答，就直接说"资料里没有提到这一点"，并给出你能确认的相邻知识。
3. 每一条关键结论后面用方括号标出依据的编号，例如 [1]、[2]；一句话可以同时引用多个。
4. 面向新手：先给结论或直接可执行的步骤，再解释原因；多用短句、少用术语，必须用术语时顺手解释一下。
5. 如果资料之间有冲突，说明冲突并给出更稳妥的做法。
6. 如果问题和 Minecraft 无关（比如做饭、写代码），只回一句"这超出了我的知识库范围"，不要编造内容、不要给替代方案。
6. 不要输出 Markdown 表格以外的花哨排版；步骤类问题用有序列表。

【资料】
{context}
"""

USER_TEMPLATE = """问题：{question}

请基于上面的【资料】回答，并在关键处标注 [编号]。"""


def format_context(hits: list[Hit]) -> str:
    """把检索片段编号成 [1] [2] ...，并附上出处文件名。"""
    if not hits:
        return "（本次没有检索到相关资料）"
    blocks: list[str] = []
    for i, hit in enumerate(hits, start=1):
        c = hit.chunk
        blocks.append(
            f"[{i}] 出处：{c.source} · {c.heading}（相关度 {hit.rel:.2f}）\n{c.text}"
        )
    return "\n\n---\n\n".join(blocks)


def build_messages(question: str, hits: list[Hit]) -> list[dict[str, str]]:
    """组装成 Ollama /api/chat 需要的 messages 结构。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(context=format_context(hits))},
        {"role": "user", "content": USER_TEMPLATE.format(question=question)},
    ]
