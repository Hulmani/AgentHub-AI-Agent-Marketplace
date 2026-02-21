from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="SummarizeAgent", version="0.1.0")


class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=1)


@app.post("/run")
def run(payload: SummarizeRequest) -> dict[str, str]:
    words = payload.text.split()
    summary = " ".join(words[:12]).strip()
    if len(words) > 12:
        summary += "..."
    return {"summary": summary}

