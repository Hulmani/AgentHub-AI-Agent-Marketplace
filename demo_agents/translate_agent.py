from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="TranslateAgent", version="0.1.0")


class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1)
    language: str = Field(..., min_length=2, max_length=32)


@app.post("/run")
def run(payload: TranslateRequest) -> dict[str, str]:
    translated = f"[{payload.language.lower()}] {payload.text}"
    return {"translation": translated}

