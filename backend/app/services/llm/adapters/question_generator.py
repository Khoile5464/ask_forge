# backend/app/services/llm/adapters/question_generator.py
import json
from typing import AsyncIterator, Optional, Dict, List

import logging
from ollama import AsyncClient

from ask_forge.backend.app.services.llm.base import LLMProvider
from ask_forge.backend.app.core.config import settings

logger = logging.getLogger(__name__)

# Ép Ollama trả JSON đúng schema để parse danh sách câu hỏi ổn định
QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["questions"],
}

QG_PROMPT = """You are a study assistant helping a student explore a topic more deeply.
The student just asked: "{question}"

Relevant excerpts from their study material:
{contexts}

Write {n} short follow-up questions the student could ask next to deepen their understanding.
Rules:
- Write every question in {lang}.
- Base the questions on the excerpts above; do not invent facts outside them.
- Do not repeat or rephrase the student's question.
- Each question is one sentence and ends with a question mark.

Return JSON: {{"questions": ["...", "..."]}}"""


class QuestionGeneratorAdapter(LLMProvider):
    """
    ✅ Adapter sinh câu hỏi gợi ý (follow-up questions) bằng model chạy qua Ollama
    """

    def __init__(self, model: str):
        self.model = model
        self._client = AsyncClient(host=settings.OLLAMA_BASE_URL)

    async def generate(
            self,
            prompt: str,
            contexts: List[Dict] = None,
            n: int = 5,
            lang: str = "vietnamese",
            history_block: str = "",
            summary_block: str = "",
            **kwargs
    ) -> List[str]:
        """
        ✅ Main generate method - returns list of questions
        """
        user_prompt = QG_PROMPT.format(
            question=prompt,
            contexts=self._format_contexts(contexts) or "(no excerpts)",
            n=n,
            lang=self._language_name(lang),
        )

        response = await self._client.chat(
            model=self.model,
            messages=[{"role": "user", "content": user_prompt}],
            format=QUESTIONS_SCHEMA,
            options={"temperature": 0.7, "num_predict": 512},
        )

        try:
            questions = json.loads(response["message"]["content"]).get("questions", [])
        except (json.JSONDecodeError, AttributeError):
            logger.warning("⚠️ QG model returned invalid JSON")
            questions = []

        questions = self._filter_questions(questions, seed=prompt)[:n]
        logger.info(f"✅ Generated {len(questions)}/{n} questions")
        return questions

    @staticmethod
    def _language_name(lang: str) -> str:
        return "English" if lang.lower() in ("en", "english") else "Vietnamese"

    def _format_contexts(self, contexts: Optional[List[Dict]]) -> str:
        """Format contexts list into string"""
        if not contexts:
            return ""

        formatted = []
        for i, ctx in enumerate(contexts[:3], 1):  # Top 3 contexts
            text = ctx.get("text", "")[:500]  # Limit to 500 chars
            formatted.append(f"[{i}] {text}")

        return "\n".join(formatted)

    def _filter_questions(self, questions: List, seed: str = "") -> List[str]:
        # TODO: Nếu như m muốn chỉnh sửa thêm bộ lọc để lọc ra những question chất lượng thì làm ở đây
        seen = {seed.strip().lower()}
        result = []
        for q in questions:
            if not isinstance(q, str):
                continue
            q = q.strip()
            if q and q.lower() not in seen:
                seen.add(q.lower())
                result.append(q)
        return result

    async def generate_stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Not implemented for QG - questions are generated in batch"""
        raise NotImplementedError("QG does not support streaming")

    @property
    def model_name(self) -> str:
        return f"ollama:{self.model}"

    @property
    def supports_streaming(self) -> bool:
        return False
