# backend/main.py

import asyncio
import json
import threading
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import numpy as np
from RealtimeSTT import AudioToTextRecorder
from scipy.signal import resample
import uvicorn

# 导入自定义的模块
from config import OPENAI_TOKEN
from utils.tts_engine import TTSEngine
from utils.llm_engine import LLMEngine

MESSAGE_HEAD_LENGTH = 4

exit_event = threading.Event()

# 初始化FastAPI应用
app = FastAPI()

# 初始化引擎
tts_engine = TTSEngine()
llm_engine = LLMEngine(OPENAI_TOKEN)

# 全局事件循环
main_event_loop = asyncio.get_event_loop()


async def process_text(session, text):
    # append user question
    session["history"].append({"role": "user", "content": text})

    # generate response
    assistant_text = await llm_engine.generate_response(session["history"])
    print("assistant_text: " + assistant_text)

    # update assistant answer
    session["history"].append({"role": "assistant", "content": assistant_text})

    # convert to audo
    audio_chunks = []
    async for chunk in tts_engine.synthesize(assistant_text):
        audio_chunks.append(chunk)
    response_audio = b"".join(audio_chunks)
    await session['websocket'].send_bytes(response_audio)


# 存储会话信息
sessions = {}


def decode_and_resample(
        audio_data,
        original_sample_rate,
        target_sample_rate):

    # Decode 16-bit PCM data to numpy array
    audio_np = np.frombuffer(audio_data, dtype=np.int16)

    # Calculate the number of samples after resampling
    num_original_samples = len(audio_np)
    num_target_samples = int(num_original_samples * target_sample_rate /
                                original_sample_rate)

    # Resample the audio
    resampled_audio = resample(audio_np, num_target_samples)

    return resampled_audio.astype(np.int16).tobytes()


def recorder_thread(session, recorder_ready_event):
    recorder_config = {
        'spinner': False,
        'use_microphone': False,
        'model': 'tiny',
        'device': 'cpu',
        'language': 'en',
        'silero_sensitivity': 0.4,
        'webrtc_sensitivity': 2,
        'post_speech_silence_duration': 0.7,
        'min_length_of_recording': 0,
        'min_gap_between_recordings': 0,
        'enable_realtime_transcription': True,
        'realtime_processing_pause': 0,
        'realtime_model_type': 'tiny.en',
    }
    
    print("Initializing RealtimeSTT...")
    
    recorder = AudioToTextRecorder(**recorder_config)
    session.update({
        "recorder": recorder,
    })
    print("RealtimeSTT initialized")
    recorder_ready_event.set()
    try:
        while not exit_event.is_set():
            full_sentence = recorder.text()
            # 使用 run_coroutine_threadsafe 将协程提交到主事件循环
            future = asyncio.run_coroutine_threadsafe(
                process_text(session, full_sentence),
                main_event_loop
            )
            # 可选地，处理 future 的结果或异常
            try:
                future.result()
            except Exception as e:
                raise e
                print(f"Error in process_text: {e}")
    finally:
        print("Shutting down recorder...")
        recorder.shutdown()


@app.get("/")
async def get():
    return {"message": "LLM 语音聊天服务正在运行"}


# WebSocket端点
@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    recorder_ready = threading.Event()

    if session_id not in sessions:
        sessions[session_id] = {
            "history": [
                {"role": "system", "content": "You are a voice assistant which can chat with the people."}
            ],
            "websocket": websocket,
        }

    session = sessions[session_id]

    print("session before model initialized:")
    print(session)

    _thread = threading.Thread(
        target=recorder_thread,
        kwargs={"session": session, "recorder_ready_event": recorder_ready},
        name="recorder thread - " + session_id,
        daemon=True,
    )
    _thread.start()
    recorder_ready.wait()

    print("session after model initialized:")
    print(session)

    await websocket.accept()

    while not exit_event.is_set():
        try:
            message = await websocket.receive_bytes()
            # 解析消息内容
            metadata_length = int.from_bytes(message[:MESSAGE_HEAD_LENGTH], byteorder='little')
            metadata_json = message[MESSAGE_HEAD_LENGTH: MESSAGE_HEAD_LENGTH+metadata_length].decode('utf-8')
            metadata = json.loads(metadata_json)
            sample_rate = metadata['sampleRate']
            chunk = message[MESSAGE_HEAD_LENGTH + metadata_length:]
            resampled_chunk = decode_and_resample(chunk, sample_rate, 16000)
            
            session['recorder'].feed_audio(resampled_chunk)
        except WebSocketDisconnect:
            print(f"Client {session_id} disconnected")
            session['recorder'].shutdown()
            if session_id in sessions:
                del sessions[session_id]
            break
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    try:
        uvicorn.run("main:app", host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        exit_event.set()
        print("Received exit signal, shutting down...")
