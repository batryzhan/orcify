"""Smart Routing, Этап 1: классификация намерения в бизнес-домен."""

from __future__ import annotations

from app.config import Settings
from app.core.llm_client import ChatMessage, LLMClient, StructuredResponse
from app.core.prompts import PromptLoader
from app.schemas.intent import IntentClassificationResult

INTENT_PROMPT = "intent_classifier"


class IntentRouter:
    def __init__(self, llm: LLMClient, prompts: PromptLoader, settings: Settings) -> None:
        self._llm = llm
        self._prompts = prompts
        self._min_confidence = settings.intent_min_confidence

    async def classify(self, text: str) -> StructuredResponse[IntentClassificationResult]:
        messages = [
            ChatMessage(role="system", content=self._prompts.load(INTENT_PROMPT)),
            ChatMessage(role="user", content=text),
        ]
        return await self._llm.structured(messages, IntentClassificationResult, stage="classifying_intent")

    def is_confident(self, result: IntentClassificationResult) -> bool:
        return result.confidence >= self._min_confidence
