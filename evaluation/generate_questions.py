from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pickle
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
INDEX_DIR = PROJECT_ROOT / "knowledge_base" / "samples" / "vector_store" / "bge-large-zh"
DEFAULT_OUTPUT = PROJECT_ROOT / "evaluation" / "coal_mine_qa_300.jsonl"


def load_config() -> tuple[str, str, str]:
    # Reuse the application's compatibility-safe, non-logging configuration.
    from backend_fastapi.main import DEFAULT_MODEL, LLM_API_KEY, LLM_API_URL

    return LLM_API_URL, LLM_API_KEY, DEFAULT_MODEL


def load_metadata() -> list[dict[str, Any]]:
    with (INDEX_DIR / "index.pkl").open("rb") as file:
        raw = pickle.load(file)
    result = []
    for position, item in enumerate(raw):
        metadata = item if isinstance(item, dict) else {"content": str(item)}
        result.append(
            {
                **metadata,
                "content": metadata.get("content") or metadata.get("text") or "",
                "source": metadata.get("file") or metadata.get("source") or "未知来源",
                "chunk_id": position,
            }
        )
    return result


def usable(document: dict[str, Any]) -> bool:
    text = document["content"].strip()
    if not 120 <= len(text) <= 900:
        return False
    if text.count("\t") > 5:
        return False
    digit_ratio = sum(character.isdigit() for character in text) / max(len(text), 1)
    return digit_ratio < 0.35 and len(set(text)) > 30


def evenly_pick(items: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count <= 0:
        return []
    if len(items) <= count:
        return items
    step = len(items) / count
    return [items[min(int((index + 0.5) * step), len(items) - 1)] for index in range(count)]


def stratified_sample(documents: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for document in documents:
        if usable(document):
            grouped[document["source"]].append(document)
    sources = sorted(grouped)
    base, remainder = divmod(count, len(sources))
    selected_by_source = {
        source: evenly_pick(grouped[source], base + int(index < remainder))
        for index, source in enumerate(sources)
    }
    selected = []
    # Interleave sources so every API batch receives diverse material.
    for position in range(max(map(len, selected_by_source.values()))):
        for source in sources:
            if position < len(selected_by_source[source]):
                selected.append(selected_by_source[source][position])
    if len(selected) != count:
        raise RuntimeError(f"可用片段不足：expected={count}, selected={len(selected)}")
    return selected


def prompt_for(batch: list[dict[str, Any]]) -> str:
    materials = []
    for item in batch:
        avoid = item.get("_avoid_questions", [])
        avoid_instruction = ""
        if avoid:
            avoid_instruction = "\n请换一个信息点提问，不得重复这些问题：" + "；".join(avoid)
        materials.append(
            f'<item id="{item["chunk_id"]}" source="{item["source"]}">\n'
            f'{item["content"]}{avoid_instruction}\n</item>'
        )
    return (
        "你正在构建煤矿安全知识检索评测集。请针对每个资料片段生成1个中文问题。\n"
        "要求：问题必须能仅依据对应片段回答；使用真实用户可能采用的自然表达；"
        "不得出现‘根据材料/上述/本文’等指代；不要泄露答案；不同问题尽量覆盖规定查询、"
        "原因、条件、处置措施、参数和职责等类型。\n"
        "只返回严格JSON：{\"items\":[{\"id\":数字,\"question\":\"问题\"}]}；"
        "不得输出Markdown或解释。\n\n" + "\n\n".join(materials)
    )


def parse_questions(content: str) -> dict[int, str]:
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end <= start:
        return {}
    payload = json.loads(content[start : end + 1])
    result = {}
    for item in payload.get("items", []):
        question = str(item.get("question", "")).strip()
        if 6 <= len(question) <= 120 and not re.search(r"根据(?:材料|上述|本文)", question):
            result[int(item["id"])] = question
    return result


async def generate_batch(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    batch: list[dict[str, Any]],
    api_url: str,
    api_key: str,
    model: str,
) -> dict[int, str]:
    async with semaphore:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.post(
                    api_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt_for(batch)}],
                        "thinking": {"type": "disabled"},
                        "temperature": 0.7,
                        "max_tokens": 2200,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                parsed = parse_questions(content)
                if len(parsed) == len(batch):
                    return parsed
                last_error = ValueError(f"返回数量不完整：{len(parsed)}/{len(batch)}")
            except Exception as exc:
                last_error = exc
            await asyncio.sleep(2**attempt)
        raise RuntimeError(f"问题生成失败：{type(last_error).__name__}: {last_error}")


def relevant_neighbors(document: dict[str, Any], all_documents: list[dict[str, Any]]) -> list[int]:
    chunk_id = document["chunk_id"]
    source = document["source"]
    relevant = [chunk_id]
    for neighbor in (chunk_id - 1, chunk_id + 1):
        if 0 <= neighbor < len(all_documents) and all_documents[neighbor]["source"] == source:
            relevant.append(neighbor)
    return sorted(relevant)


async def run(args: argparse.Namespace) -> None:
    documents = load_metadata()
    selected = stratified_sample(documents, args.count)
    api_url, api_key, configured_model = load_config()
    model = args.model or configured_model
    if not api_url.startswith("http") or not api_key:
        raise RuntimeError("模型 API 尚未正确配置")

    checkpoint = args.output.with_suffix(args.output.suffix + ".partial.json")
    generated: dict[int, str] = {}
    if checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        generated = {int(chunk_id): question for chunk_id, question in saved.items()}
        print(f"恢复断点：已完成 {len(generated)}/{len(selected)} 条", flush=True)
    selected_ids = {item["chunk_id"] for item in selected}
    generated = {chunk_id: question for chunk_id, question in generated.items() if chunk_id in selected_ids}
    pending = [item for item in selected if item["chunk_id"] not in generated]
    batches = [pending[index : index + args.batch_size] for index in range(0, len(pending), args.batch_size)]
    timeout = httpx.Timeout(args.request_timeout, connect=20.0)
    semaphore = asyncio.Semaphore(args.concurrency)
    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [
            asyncio.create_task(generate_batch(client, semaphore, batch, api_url, api_key, model))
            for batch in batches
        ]
        for task in asyncio.as_completed(tasks):
            result = await task
            generated.update(result)
            checkpoint.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"生成进度：{len(generated)}/{len(selected)} 条", flush=True)

    selected_by_id = {item["chunk_id"]: item for item in selected}
    for dedup_round in range(3):
        seen: dict[str, tuple[int, str]] = {}
        duplicates: list[dict[str, Any]] = []
        for chunk_id, question in generated.items():
            normalized = re.sub(r"\W+", "", question)
            if normalized in seen:
                duplicate = dict(selected_by_id[chunk_id])
                duplicate["_avoid_questions"] = [question, seen[normalized][1]]
                duplicates.append(duplicate)
            else:
                seen[normalized] = (chunk_id, question)
        if not duplicates:
            break
        print(f"去重重生成：{len(duplicates)} 条（第 {dedup_round + 1} 轮）", flush=True)
        async with httpx.AsyncClient(timeout=timeout) as client:
            replacement = await generate_batch(
                client,
                asyncio.Semaphore(1),
                duplicates,
                api_url,
                api_key,
                model,
            )
        generated.update(replacement)
        checkpoint.write_text(json.dumps(generated, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        raise RuntimeError("重复问题重生成 3 轮后仍未通过")

    seen_questions: set[str] = set()
    records = []
    for index, document in enumerate(selected, 1):
        question = generated[document["chunk_id"]]
        normalized = re.sub(r"\W+", "", question)
        if normalized in seen_questions:
            raise RuntimeError(f"发现重复问题：{question}")
        seen_questions.add(normalized)
        records.append(
            {
                "id": f"q{index:04d}",
                "question": question,
                "target_chunk_id": document["chunk_id"],
                "relevant_chunk_ids": relevant_neighbors(document, documents),
                "relevant_sources": [document["source"]],
                "source": document["source"],
                "snippet_sha256": hashlib.sha256(document["content"].encode("utf-8")).hexdigest()[:16],
                "generator_model": model,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
    source_counts: dict[str, int] = defaultdict(int)
    for record in records:
        source_counts[record["source"]] += 1
    print(
        json.dumps(
            {
                "output": str(args.output),
                "questions": len(records),
                "unique_questions": len(seen_questions),
                "source_distribution": source_counts,
                "model": model,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--request-timeout", type=float, default=600.0)
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
