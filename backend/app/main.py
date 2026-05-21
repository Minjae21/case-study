from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent import run_agent

app = FastAPI(title="PartSelect Chat Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    session_id: str = ""


class ProductCard(BaseModel):
    part_number: str
    title: str
    price: str
    image_url: str
    url: str
    appliance_type: str


class ChatResponse(BaseModel):
    role: str
    content: str
    products: list[ProductCard] = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="messages cannot be empty")

    messages = [
        {"role": m.role, "content": m.content}
        for m in req.messages
        if m.role in ("user", "assistant") and m.content.strip()
    ]

    if not messages or messages[0]["role"] != "user":
        raise HTTPException(status_code=400, detail="First message must be from user")

    try:
        result = run_agent(messages)
    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            return ChatResponse(
                role="assistant",
                content="I'm getting a lot of requests right now — please wait a moment and try again.",
                products=[],
            )
        raise
    return ChatResponse(
        role=result["role"],
        content=result["content"],
        products=[ProductCard(**p) for p in result.get("products", [])],
    )
