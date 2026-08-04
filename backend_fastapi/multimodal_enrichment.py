from __future__ import annotations

import base64
import importlib.util
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx


def _enabled(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return os.getenv(name, fallback).strip().lower() in {"1", "true", "yes", "on"}


def ocr_available() -> bool:
    return any(
        importlib.util.find_spec(module) is not None
        for module in ("rapidocr_onnxruntime", "rapidocr_paddle")
    )


def vision_available() -> bool:
    return bool(
        _enabled("VISION_DESCRIPTION_ENABLED")
        and os.getenv("VISION_API_URL", "").strip()
        and os.getenv("VISION_MODEL_NAME", "").strip()
    )


def run_ocr(image_path: Path) -> tuple[str, dict[str, Any]]:
    if not _enabled("MULTIMODAL_OCR_ENABLED", True):
        return "", {"ocr_status": "disabled"}
    if not ocr_available():
        return "", {"ocr_status": "unavailable"}
    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr_paddle import RapidOCR
        engine = RapidOCR()
        result, _ = engine(str(image_path))
        rows = result or []
        texts: list[str] = []
        scores: list[float] = []
        for row in rows:
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            text = str(row[1]).strip()
            if text:
                texts.append(text)
                try:
                    scores.append(float(row[2]))
                except (TypeError, ValueError):
                    pass
        return "\n".join(texts), {
            "ocr_status": "completed",
            "ocr_lines": len(texts),
            "ocr_average_confidence": round(sum(scores) / len(scores), 4) if scores else None,
        }
    except Exception as exc:
        return "", {"ocr_status": "failed", "ocr_error": type(exc).__name__}


def describe_image(image_path: Path, context: str = "") -> tuple[str, dict[str, Any]]:
    if not _enabled("VISION_DESCRIPTION_ENABLED"):
        return "", {"vision_status": "disabled"}
    api_url = os.getenv("VISION_API_URL", "").strip()
    model = os.getenv("VISION_MODEL_NAME", "").strip()
    if not api_url or not model:
        return "", {"vision_status": "unconfigured"}
    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    prompt = (
        "请准确描述这张煤矿安全资料图片中的设备、文字、数值、连线、流程和相互关系。"
        "不得推测图中不存在的信息；如果无法辨认请明确说明。输出适合知识库检索的一段中文描述。"
    )
    if context:
        prompt += f"\n相邻文档上下文：{context[:1000]}"
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("VISION_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": int(os.getenv("VISION_MAX_TOKENS", "512")),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    },
                ],
            }
        ],
    }
    try:
        response = httpx.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=float(os.getenv("VISION_TIMEOUT_SECONDS", "60")),
        )
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices") or []
        description = ""
        if choices:
            description = str((choices[0].get("message") or {}).get("content") or "").strip()
        return description, {
            "vision_status": "completed" if description else "empty",
            "vision_model": model,
            "vision_usage": body.get("usage") or {},
        }
    except Exception as exc:
        return "", {"vision_status": "failed", "vision_error": type(exc).__name__}


def enrichment_capabilities() -> dict[str, Any]:
    return {
        "ocr_installed": ocr_available(),
        "ocr_enabled": _enabled("MULTIMODAL_OCR_ENABLED", True),
        "vision_configured": vision_available(),
        "vision_enabled": _enabled("VISION_DESCRIPTION_ENABLED"),
    }
