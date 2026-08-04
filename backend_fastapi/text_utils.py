from __future__ import annotations

import re
import math
from typing import Any


def normalize_citations(answer: str, source_count: int) -> str:
    answer = re.sub(r"\[(?:#|＃)?\s*(\d+)\]", r"[#\1]", answer)

    def keep_valid(match: re.Match[str]) -> str:
        citation_id = int(match.group(1))
        return match.group(0) if 1 <= citation_id <= source_count else ""

    return re.sub(r"\[#(\d+)\]", keep_valid, answer).strip()


def estimate_tokens(text: str) -> int:
    """Cheap estimate used only when the provider does not report usage."""
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    non_cjk = re.sub(r"[\u3400-\u9fff\s]", "", text)
    return cjk_count + math.ceil(len(non_cjk) / 4)


def citation_metrics(answer: str, source_count: int) -> dict[str, Any]:
    citation_ids = {
        int(value)
        for value in re.findall(r"\[#(\d+)\]", answer)
        if 1 <= int(value) <= source_count
    }
    sentences = [
        value.strip()
        for value in re.split(r"(?<=[。！？!?；;])|\n+", answer)
        if len(re.sub(r"\[#\d+\]", "", value).strip()) >= 6
    ]
    cited_sentences = sum(bool(re.search(r"\[#\d+\]", value)) for value in sentences)
    return {
        "available_sources": source_count,
        "cited_sources": len(citation_ids),
        "source_utilization": round(len(citation_ids) / source_count, 4) if source_count else 0.0,
        "substantive_sentences": len(sentences),
        "cited_sentences": cited_sentences,
        "citation_coverage": round(cited_sentences / len(sentences), 4) if sentences else 0.0,
    }
