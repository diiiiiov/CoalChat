from __future__ import annotations

import re


def normalize_citations(answer: str, source_count: int) -> str:
    answer = re.sub(r"\[(?:#|＃)?\s*(\d+)\]", r"[#\1]", answer)

    def keep_valid(match: re.Match[str]) -> str:
        citation_id = int(match.group(1))
        return match.group(0) if 1 <= citation_id <= source_count else ""

    return re.sub(r"\[#(\d+)\]", keep_valid, answer).strip()
