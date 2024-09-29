import asyncio
import base64
import json
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import numpy as np
from RealtimeSTT import AudioToTextRecorder
from scipy.signal import resample

from utils.tts_engine import TTSEngine
from utils.llm_engine import LLMEngine


MESSAGE_HEAD_LENGTH = 4


class Session:
    def __init__(self, websocket: WebSocket, session_id: str, loop: asyncio.AbstractEventLoop, llm_engine: LLMEngine, tts_engine: TTSEngine):
        self.websocket = websocket
        self.session_id = session_id
        self.history = [
            {"role": "system", "content": "You are a voice assistant that can chat with people."}
        ]
        self.recorder = None
        self.recorder_thread = None
        self.exit_event = threading.Event()
        self.loop = loop
        self.llm_engine = llm_engine
        self.tts_engine = tts_engine
        self.recorder_ready = threading.Event()
        self.recorder_config = {
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

    async def start(self):
        # Start the recorder thread
        self.recorder_thread = threading.Thread(
            target=self.recorder_thread_func,
            name="recorder thread - " + self.session_id,
            daemon=True,
        )
        self.recorder_thread.start()
        self.recorder_ready.wait()
        await self.websocket.accept()
        # Start receiving messages
        await self.receive_messages()

    async def stop(self):
        # Signal exit
        self.exit_event.set()
        # Clean up resources
        if self.recorder:
            # Feed dummy data to unblock the queue
            try:
                self.recorder.audio_queue.put_nowait(b'')
            except Exception as e:
                print(f"Error feeding dummy data: {e}")
            self.recorder.shutdown()

        # Wait for the recorder thread to finish
        if self.recorder_thread and self.recorder_thread.is_alive():
            self.recorder_thread.join(timeout=1)
        # Close the websocket if it's not already closed
        if not self.websocket.client_state.name == 'DISCONNECTED':
            await self.websocket.close()
        print(f"Session {self.session_id} stopped.")

    def recorder_thread_func(self):
        print("Initializing RealtimeSTT...")
        self.recorder = AudioToTextRecorder(**self.recorder_config)
        print("RealtimeSTT initialized")
        self.recorder_ready.set()
        try:
            while not self.exit_event.is_set():
                full_sentence = self.recorder.text()
                if full_sentence == "":
                    continue
                # Process text
                future = asyncio.run_coroutine_threadsafe(
                    self.process_text(full_sentence),
                    self.loop
                )
                try:
                    future.result()
                except Exception as e:
                    print(f"Error in process_text: {e}")
        except Exception as e:
            print(f"Recorder thread exception: {e}")
        finally:
            print("Shutting down recorder...")
            if self.recorder:
                self.recorder.shutdown()

    async def process_text(self, text):
        # Append user question
        self.history.append({"role": "user", "content": text})

        # Send status to frontend to indicate processing started
        await self.websocket.send_json({"type": "status", "value": "analysing"})

        # Generate response
        assistant_text = await self.llm_engine.generate_response(self.history)
        print("assistant_text: " + assistant_text)

        # Update assistant answer
        self.history.append({"role": "assistant", "content": assistant_text})

        # Convert to audio
        audio_chunks = []
        async for chunk in self.tts_engine.synthesize(assistant_text):
            audio_chunks.append(chunk)
        response_audio = b"".join(audio_chunks)

        # Encode audio data as base64
        audio_base64 = base64.b64encode(response_audio).decode('utf-8')

        # Send audio data as JSON
        await self.websocket.send_json({"type": "audio", "value": audio_base64})

    def decode_and_resample(self, audio_data, original_sample_rate, target_sample_rate):
        # Decode 16-bit PCM data to numpy array
        audio_np = np.frombuffer(audio_data, dtype=np.int16)

        # Calculate the number of samples after resampling
        num_original_samples = len(audio_np)
        num_target_samples = int(num_original_samples * target_sample_rate /
                                 original_sample_rate)

        # Resample the audio
        resampled_audio = resample(audio_np, num_target_samples)

        return resampled_audio.astype(np.int16).tobytes()

    async def receive_messages(self):
        while not self.exit_event.is_set():
            try:
                message = await self.websocket.receive_bytes()
                # Parse message
                metadata_length = int.from_bytes(message[:MESSAGE_HEAD_LENGTH], byteorder='little')
                metadata_json = message[MESSAGE_HEAD_LENGTH: MESSAGE_HEAD_LENGTH+metadata_length].decode('utf-8')
                metadata = json.loads(metadata_json)
                sample_rate = metadata['sampleRate']
                chunk = message[MESSAGE_HEAD_LENGTH + metadata_length:]
                resampled_chunk = self.decode_and_resample(chunk, sample_rate, 16000)
                self.recorder.feed_audio(resampled_chunk)
            except WebSocketDisconnect:
                print(f"Client {self.session_id} disconnected")
                await self.stop()
                break
            except Exception as e:
                print(f"Error: {e}")
                await self.stop()
                break
