"""
Application State Manager - Quản lý lifecycle và global resources.

Singleton pattern để đảm bảo chỉ có 1 instance ChromaDB, checkpoints, etc.
Khởi tạo khi app startup, cleanup khi shutdown.
"""
import asyncio
from functools import lru_cache
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import logging

from ask_forge.backend.app.repositories.vectorstore import ChromaRepo
from ask_forge.backend.app.core.config import settings
from ask_forge.backend.app.services.chat_history.chat_history import InMemoryHistoryRepo
from ask_forge.backend.app.services.llm.adapters.question_generator import QuestionGeneratorAdapter

from ask_forge.backend.app.services.llm.registry import get_registry, LLMRegistry
from ask_forge.backend.app.services.llm.router import LLMRouter, prefer_local_for_qg, route_chat_by_provider

from ask_forge.backend.app.services.llm.adapters.gemini import GeminiAdapter
from ask_forge.backend.app.services.llm.adapters.ollama import OllamaAdapter
from ollama import AsyncClient as OllamaClient

from pathlib import Path

from ask_forge.backend.app.services.queue.async_queue import AsyncBackgroundQueue
from ask_forge.backend.app.services.queue.redis_queue import BackgroundQueueUsingRedis

logger = logging.getLogger(__name__)

CORE_DIR = Path(__file__).resolve().parent  # …/backend/app/core
APP_DIR = CORE_DIR.parent  # …/backend/app
BACKEND_DIR = APP_DIR.parent  #     …/backend
PROJECT_ROOT = BACKEND_DIR.parent  # …/ask_forge

class AppState:
    """
    Singleton class quản lý tất cả global resources của application.

    Attributes:
        chroma_repo: ChromaDB repository instance (singleton)
        loaded_models: Dictionary chứa các ML models đã load
        active_indexes: Set các index names đang tồn tại
    """
    _instance: Optional["AppState"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # Đặt cờ cho lần khởi tạo đầu tiên của instance
            cls._instance._constructed = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_constructed", False):
            return

        # ---- Fields chỉ tạo 1 lần ----
        self._init_lock = asyncio.Lock()   # Lock để tránh race khi startup
        self._initialized = False          # Chỉ True sau khi startup xong

        self.chroma_repo: Optional[ChromaRepo] = None
        self.loaded_models: Dict[str, Any] = {}
        self.active_indexes: set[str] = set()

        self.llm_registry: LLMRegistry = get_registry() # Đăng kí một singleton LLMRegistry
        self.llm_router = LLMRouter()

        # # Background Queue Using Redis
        # self.bq = BackgroundQueueUsingRedis(
        #     redis_url=settings.REDIS_URL,
        # )

        # Use AsyncIO queue instead of Redis/RQ
        self.bq = AsyncBackgroundQueue()

        # History repo
        self.history_repo = InMemoryHistoryRepo(
            default_last_k=12,
            max_turns_per_session=800)

        # --------------------------------
        self._constructed = True
        logger.info("AppState constructed")

    # ------------------------------
    # App lifecycle
    # ------------------------------
    async def startup(self):
        """
        Khởi tạo chroma_repo, ensure_hf_model.
        Gọi hàm này trong FastAPI lifespan event.
        """
        async with self._init_lock:
            if self._initialized:
                return

            logger.info("🚀 Starting up application resources...")

            # 1) Khởi tạo ChromaDB
            try:
                logger.info("📦 Initializing ChromaDB repository...")
                self.chroma_repo = ChromaRepo()

                # Load danh sách các collections hiện có
                collections = self.chroma_repo.list_collections()

                self.active_indexes = {col.name for col in collections}
                logger.info(
                    "✅ ChromaDB ready. Found %d existing indexes: %s",
                    len(self.active_indexes), self.active_indexes
                )
            except Exception as e:
                logger.exception(f"❌ Failed to initialize ChromaDB. Error: {e}")
                # _initialized vẫn False nếu fail
                raise

            # Use
            logger.info("🔌 Registering LLM providers...")

            # Gemini
            self.llm_registry.register("gemini_service", GeminiAdapter())

            # Ollama: chat (tuỳ chọn của người dùng) + Question Generator
            self.llm_registry.register("ollama_service", OllamaAdapter(settings.OLLAMA_CHAT_MODEL))
            self.llm_registry.register(
                "question_generator_service",
                QuestionGeneratorAdapter(settings.OLLAMA_QG_MODEL)
            )
            await self._check_ollama_models()

            # Setup router policies
            self.llm_router.add_policy(route_chat_by_provider)
            self.llm_router.add_policy(prefer_local_for_qg)

            logger.info(f"✅ LLM providers ready: {self.llm_registry.list_providers()}")

            self._initialized = True
            logger.info("✅ All application resources started successfully")

    async def _check_ollama_models(self):
        """Chỉ cảnh báo (không crash) nếu Ollama chưa chạy hoặc thiếu model"""
        required = {settings.OLLAMA_EMBED_MODEL, settings.OLLAMA_QG_MODEL, settings.OLLAMA_CHAT_MODEL}
        try:
            listed = await OllamaClient(host=settings.OLLAMA_BASE_URL).list()
        except Exception as e:
            logger.warning(f"⚠️ Cannot reach Ollama at {settings.OLLAMA_BASE_URL}: {e}")
            return

        available = {m["model"] for m in listed["models"]}
        available |= {name.removesuffix(":latest") for name in available}
        missing = sorted(required - available)
        if missing:
            logger.warning(f"⚠️ Ollama models not pulled yet: {missing} → run `ollama pull <model>`")
        else:
            logger.info(f"✅ Ollama models ready: {sorted(required)}")

    async def shutdown(self):
        """
        Cleanup resources khi app shutdown.
        """
        logger.info("🛑 Shutting down application resources...")

        # Cleanup ChromaDb nếu cần
        if self.chroma_repo:
            try:
                # Nếu có handle close/flush, gọi ở đây (ChromaRepo optional)
                logger.info("📦 ChromaDB persisted to disk")
            finally:
                self.chroma_repo = None

        if self.loaded_models:
            logger.info("🧠 Unloading ML models...")
            self.loaded_models.clear()

        self._initialized = False
        logger.info("✅ All resources cleaned up")

    def get_chroma_repo(self) -> ChromaRepo:
        """
        Lấy ChromaDB repository instance.

        Raises:
            RuntimeError: Nếu chưa được khởi tạo (startup chưa chạy)
        """
        if self.chroma_repo is None:
            raise RuntimeError(
                "ChromaDB not initialized. Make sure app_state.startup() was called."
            )
        return self.chroma_repo

    def refresh_active_indexes(self):
        """Đồng bộ lại active_indexes từ Chroma khi có thay đổi ngoài luồng."""
        if not self.chroma_repo:
            raise RuntimeError("ChromaDB not initialized. Make sure app_state.startup() was called.")
        cols = self.chroma_repo.list_collections()
        self.active_indexes = {c.name for c in cols}

    def register_index(self, index_name: str):
        """Đăng ký index mới vào active set."""
        self.active_indexes.add(index_name)
        logger.info("📝 Registered index: %s", index_name)

    def unregister_index(self, index_name: str):
        self.active_indexes.discard(index_name)
        logger.info("🗑️ Unregistered index: %s", index_name)

    def index_exists(self, index_name: str) -> bool:
        """Kiểm tra xem index có tồn tại không."""
        return index_name in self.active_indexes

# ---- The SINGLE way to obtain AppState everywhere ----
@lru_cache(maxsize=1)
def get_app_state() -> AppState:
    return AppState()


app_state = get_app_state() # <- dùng đúng cùng 1 instance
@asynccontextmanager
async def lifespan_manager(app):
    """
        FastAPI lifespan context manager.

        Usage trong main.py:
            app = FastAPI(lifespan=lifespan_manager)
        """
    await app_state.startup()
    app.state.app_state = app_state

    try:
        yield
    finally:
        await app_state.shutdown()
