# backend/utils/stt_engine.py
import whisper
import numpy as np

class STTEngine:
    def __init__(self, model_size="base"):
        self.model = whisper.load_model(model_size)

    async def transcribe(self, audio_data):
        # 将音频数据转换为numpy数组
        audio = np.frombuffer(audio_data, np.int16).astype(np.float32) / 32768.0
        # 使用Whisper模型进行转录
        result = self.model.transcribe(audio)
        return result['text']
