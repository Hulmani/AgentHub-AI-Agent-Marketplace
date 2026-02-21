import re

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="KeywordExtractAgent", version="0.1.0")

STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "is",
    "it",
    "for",
    "on",
    "with",
    "this",
    "that",
}


class KeywordRequest(BaseModel):
    text: str = Field(..., min_length=1)


@app.post("/run")
def run(payload: KeywordRequest) -> dict[str, list[str]]:
    tokens = re.findall(r"[a-zA-Z0-9]+", payload.text.lower())
    keywords: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in STOP_WORDS or token in seen or len(token) < 3:
            continue
        keywords.append(token)
        seen.add(token)
        if len(keywords) == 8:
            break
    return {"keywords": keywords}

