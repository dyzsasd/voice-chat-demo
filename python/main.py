# backend/main.py

import asyncio
import os

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import uvicorn

from config import OPENAI_TOKEN, ROOT_DIR
from utils.tts_engine import TTSEngine
from utils.llm_engine import LLMEngine
from session import Session


# Initialize FastAPI app
app = FastAPI()

frontend_dir = os.path.join(ROOT_DIR, '../app')

# Mount the 'frontend' directory as static files
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def read_index():
    return FileResponse(f'{frontend_dir}/index.html')


# Initialize engines
tts_engine = TTSEngine(voice="en-US-AnaNeural")
llm_engine = LLMEngine(OPENAI_TOKEN)

active_connections = set()

@app.get("/health")
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
