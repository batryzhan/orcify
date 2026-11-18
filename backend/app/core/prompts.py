"""Единый загрузчик системных промптов из ``backend/prompts/``.

Промпты не хранятся в .py-файлах. Подстановка переменных — через
``string.Template`` (``$today``), отсутствующая переменная — ошибка.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template

_NAME_RE = re.compile(r"^[a-z0-9_]+$")


class PromptNotFoundError(LookupError):
    pass


class PromptLoader:
    def __init__(self, prompts_dir: Path) -> None:
        self._dir = prompts_dir
        self._cache: dict[str, str] = {}

    def _read(self, name: str) -> str:
        if not _NAME_RE.fullmatch(name):
            raise ValueError(f"Invalid prompt name: {name!r}")
        if name not in self._cache:
            path = self._dir / f"{name}.md"
            if not path.is_file():
                raise PromptNotFoundError(f"Prompt not found: {path.name}")
            self._cache[name] = path.read_text(encoding="utf-8").strip()
        return self._cache[name]

    def load(self, name: str, **variables: str) -> str:
        text = self._read(name)
        return Template(text).substitute(variables) if variables else text
