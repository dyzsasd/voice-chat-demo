# backend/utils/llm_engine.py

import os
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage
import asyncio


class LLMEngine:
    def __init__(self, openai_key):
        # Initialize the ChatOpenAI model
        self.chat_model = ChatOpenAI(
            model_name="gpt-4o-mini",  # or "gpt-4" if you have access
            temperature=0.7,
            openai_api_key=openai_key,
            max_retries=3
        )

    async def generate_response(self, session_history):
        # Convert session_history to LangChain's message format
        messages = self._convert_history(session_history)

        # Since LangChain's ChatOpenAI doesn't support asynchronous calls directly,
        # we'll run the blocking call in a separate thread to avoid blocking the event loop.
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, self.chat_model, messages)

        # Extract the assistant's reply
        assistant_reply = response.content
        return assistant_reply

    def _convert_history(self, session_history):
        # Convert the session history to LangChain messages
        lc_messages = []
        for message in session_history:
            role = message["role"]
            content = message["content"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
        return lc_messages
