"""How many external model calls this process has made, over HTTP.

    GET /dev/model-calls

Counts only — by task and model, never content, never a token count, never anything that
could carry a person's data (`app.llm.call_counter`'s own docstring). Only on a declared dev
run (NURA_DEV_CODE_SENDER=1), the same gate `app.channels.api.dev_clock` already holds every
other `/dev/*` door to: anywhere else there is no such route (404). Meant for a live check to
read back exactly how many calls a feed run made, the way `app.delivery.feed.background`'s own
"N external model calls this run" log line already says once per run, without needing the log."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.channels.api.deps import settings_of
from app.llm.call_counter import counts, total_calls

router = APIRouter(tags=["dev"])


class ModelCallLine(BaseModel):
    task: str
    model: str
    calls: int


class ModelCallsOut(BaseModel):
    total: int
    by_task_and_model: list[ModelCallLine]


@router.get("/dev/model-calls")
async def read_model_calls(request: Request) -> ModelCallsOut:
    """This process's external model call count, since it started. Dev runs only."""
    if not settings_of(request).dev_code_sender:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    lines = [
        ModelCallLine(task=task.value, model=model, calls=count)
        for (task, model), count in sorted(counts().items())
    ]
    return ModelCallsOut(total=total_calls(), by_task_and_model=lines)
