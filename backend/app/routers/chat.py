import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.models.schemas import ChatRequest
from app.services.rag import answer_stream

router = APIRouter()


@router.post("/chat")
async def chat(request: ChatRequest):
    history = [{"role": m.role, "content": m.content} for m in request.history]

    async def event_generator():
        async for event in answer_stream(request.question, history):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
