"""HR-домен: локальная Gemma раскладывает кадровую задачу на подзадачи для Orcify Jira."""

from __future__ import annotations

from typing import Final

from app.core.llm_client import ChatMessage, LLMClient
from app.core.prompts import PromptLoader
from app.schemas.hr import JiraPlanSchema

PLANNER_PROMPT: Final = "hr_planner"


class HrService:
    def __init__(self, llm: LLMClient, prompts: PromptLoader) -> None:
        self._llm = llm
        self._prompts = prompts

    async def plan(self, text: str) -> JiraPlanSchema:
        messages = [
            ChatMessage(role="system", content=self._prompts.load(PLANNER_PROMPT)),
            ChatMessage(role="user", content=text),
        ]
        return (await self._llm.structured(messages, JiraPlanSchema, stage="planning_tasks")).data
