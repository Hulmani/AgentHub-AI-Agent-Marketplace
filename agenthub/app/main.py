from fastapi import FastAPI

from .database import Base, engine
from .routers import agents

app = FastAPI(
    title="AgentHub API",
    version="0.1.0",
    description="MVP Agent-to-Agent Marketplace API",
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(agents.router)

