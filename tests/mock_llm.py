import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse


app = FastAPI()


@app.post("/v1/completions")
async def completions(payload: dict):
    answer = "发生透水事故后，应立即组织人员向高处撤离[#1]，并启动应急处置。[#99]"
    if not payload.get("stream"):
        return {"choices": [{"text": answer}]}

    async def events():
        for token in ("发生透水事故后，", "应立即组织人员向高处撤离", "[#1]", "，并启动应急处置。", "[#99]"):
            data = {"choices": [{"text": token}]}
            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.03)
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
