# backend/main.py

import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import numpy as np
import uvicorn
from config import OPENAI_TOKEN
from utils.tts_engine import TTSEngine
from utils.llm_engine import LLMEngine
from session import Session


# Initialize FastAPI app
app = FastAPI()

# Initialize engines
tts_engine = TTSEngine()
llm_engine = LLMEngine(OPENAI_TOKEN)

active_connections = set()

@app.get("/")
async def get():
    return {"message": "LLM voice chat service is running"}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    loop = asyncio.get_running_loop()
    session = Session(websocket, session_id, loop, llm_engine, tts_engine)
    active_connections.add(session)
    try:
        await session.start()
    finally:
        active_connections.discard(session)


@app.on_event("shutdown")
async def shutdown_event():
    print("Shutting down, closing all connections...")
    # Create a list of tasks to stop all handlers
    tasks = [conn.stop() for conn in list(active_connections)]
    if tasks:
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
