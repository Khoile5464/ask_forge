# backend/app/services/llm/adapters/ollama.py
from typing import AsyncIterator

from ollama import AsyncClient

from ask_forge.backend.app.services.llm.base import LLMProvider
from ask_forge.backend.app.core.config import settings


class OllamaAdapter(LLMProvider):
    """Chat với model chạy local qua Ollama server"""

    def __init__(self, model: str):
        self._client = AsyncClient(host=settings.OLLAMA_BASE_URL)
        self._model_name = model

    async def generate(self, prompt: str, **kwargs) -> str:
        response = await self._client.chat(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        stream = await self._client.chat(
            model=self._model_name,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        async for part in stream:
            chunk = part["message"]["content"]
            if chunk:
                yield chunk

    @property
    def model_name(self) -> str:
        return f"ollama:{self._model_name}"

    @property
    def supports_streaming(self) -> bool:
        return True
