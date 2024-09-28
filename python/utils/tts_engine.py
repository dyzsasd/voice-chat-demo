# backend/utils/tts_engine.py
import edge_tts

class TTSEngine:
    def __init__(self, voice="zh-CN-XiaoxiaoNeural"):
        self.voice = voice

    async def synthesize(self, text):
        communicate = edge_tts.Communicate(text, self.voice)
        # 返回字节数据的生成器
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]
