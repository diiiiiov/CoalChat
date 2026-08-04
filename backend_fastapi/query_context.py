from __future__ import annotations

import re
from typing import Any


_FOLLOW_UP_RE = re.compile(
    r"(?:这个|这种|上述|前者|后者|该值|该情况|它|其|那|那么|然后|继续|具体|详细|怎么办|为什么)"
)


def _message_text(message: Any) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content", message.get("text", ""))
    if isinstance(content, str):
        return content.strip()
    return ""


def compact_history(
    history: list[dict[str, Any]], current_query: str, *, max_messages: int = 6,
    max_chars: int = 3000,
) -> list[dict[str, str]]:
    """Normalize frontend history and remove the duplicated current user turn."""
    normalized: list[dict[str, str]] = []
    for message in history:
        text = _message_text(message)
        role = message.get("role") if isinstance(message, dict) else None
        if not text or role not in {"user", "assistant"}:
            continue
        normalized.append({"role": role, "content": text})
    if normalized and normalized[-1]["role"] == "user" and normalized[-1]["content"] == current_query.strip():
        normalized.pop()
    normalized = normalized[-max_messages:]
    remaining = max_chars
    result: list[dict[str, str]] = []
    for message in reversed(normalized):
        text = message["content"][-remaining:]
        if not text:
            break
        result.append({"role": message["role"], "content": text})
        remaining -= len(text)
    return list(reversed(result))


def should_rewrite(query: str, history: list[dict[str, str]]) -> bool:
    if not history:
        return False
    query = query.strip()
    return bool(_FOLLOW_UP_RE.search(query)) or len(query) <= 8


def rewrite_prompt(query: str, history: list[dict[str, str]]) -> str:
    transcript = "\n".join(f"{item['role']}: {item['content']}" for item in history)
    return (
        "请把最后一个用户问题改写成不依赖上下文的独立检索问题。\n"
        "只输出改写后的一个问题，不要回答，不要添加原文没有的事实。"
        "必须保留原问题中的数字、单位、条款号、设备名和限制条件。\n\n"
        f"对话历史：\n{transcript}\n\n当前问题：{query}\n独立问题："
    )


def clean_rewritten_query(value: str, fallback: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", value or "", flags=re.S)
    cleaned = cleaned.strip().splitlines()[0].strip(" `\"'：:") if cleaned.strip() else ""
    if not cleaned or len(cleaned) > 2000:
        return fallback
    return cleaned
