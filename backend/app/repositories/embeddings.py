"""
Embedding function cho ChromaDB, gọi model embedding chạy qua Ollama.
"""
from chromadb import Documents, EmbeddingFunction, Embeddings
from ollama import Client


class OllamaEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, model: str, host: str, batch_size: int = 32):
        self._client = Client(host=host)
        self._model = model
        self._batch_size = batch_size

    def __call__(self, input: Documents) -> Embeddings:
        # /api/embed nhận cả list → gửi theo batch thay vì từng đoạn một
        embeddings: Embeddings = []
        for i in range(0, len(input), self._batch_size):
            batch = list(input[i:i + self._batch_size])
            embeddings.extend(self._client.embed(model=self._model, input=batch)["embeddings"])
        return embeddings
