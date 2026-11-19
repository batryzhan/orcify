"""Local Anonymizer: PII-ді детерминистік токендерге ауыстыру [PERSON_1], [IIN_1]…

Екі деңгейлі анықтау (бәрі жергілікті):
1. Регулярлық өрнектер — ЖСН/БСН, телефондар, email, IBAN, карталар, ұйымдық-құқықтық
   нысаны бар компаниялар («ТОО «…»», «ИП Тегі»).
2. Жергілікті LLM (Structured Output) — аты-жөні, компания атаулары және мекенжайлар,
   олар үлгілермен ұсталмайды. Тек мәтінде шынымен бар үзінділер қабылданады
   (галлюцинациядан қорғаныс).

Сәйкестік кестесі тек ``AnonymizationSession`` нысанының жадында тұрады
және сұраныстан кейін тазаланады (``clear()``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from pydantic import JsonValue

from app.core.llm_client import ChatMessage, LLMClient, LLMError
from app.core.logger import get_logger
from app.core.prompts import PromptLoader
from app.schemas.privacy import AnonymizationReport, PiiCategory, PiiDetectionResult

PII_PROMPT: Final = "pii_detector"

log = get_logger(__name__)

_QUOTE_OPEN = "«\"“„'"
_QUOTE_CLOSE = "»\"”“'"

# Реттілік маңызды: нақтырақ үлгілер бұрын (IBAN/карта ЖСН-ден бұрын).
_PATTERNS: Final[list[tuple[PiiCategory | None, re.Pattern[str]]]] = [
    (PiiCategory.EMAIL, re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    (PiiCategory.IBAN, re.compile(r"\bKZ\d{2}(?:\s?[A-Z0-9]{4}){4}\b")),
    (PiiCategory.CARD, re.compile(r"\b\d{4}(?:[ -]?\d{4}){3}\b")),
    (PiiCategory.PHONE, re.compile(r"(?<!\d)(?:\+7|8)[\s(-]*\d{3}[\s)-]*\d{3}[\s-]*\d{2}[\s-]*\d{2}(?!\d)")),
    # 12 цифр: 5-ші цифр 4/5/6 болса — БСН (заңды тұлға түрі), әйтпесе ЖСН.
    (None, re.compile(r"(?<!\d)\d{12}(?!\d)")),
    (
        PiiCategory.COMPANY,
        re.compile(
            rf"\b(?:ТОО|АО|ООО|ОАО|ЗАО|ПК|LLP|LLC|JSC|Ltd)\s*[{_QUOTE_OPEN}][^{_QUOTE_CLOSE}\n]{{1,80}}[{_QUOTE_CLOSE}]"
        ),
    ),
    (PiiCategory.COMPANY, re.compile(r"\bИП\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.\s?[А-ЯЁ]\.?)?")),
]


def _classify_12_digits(value: str) -> PiiCategory:
    return PiiCategory.BIN if value[4] in "456" else PiiCategory.IIN


_LEGAL_FORM = re.compile(r"^(?:ТОО|АО|ООО|ОАО|ЗАО|ПК|ИП|LLP|LLC|JSC|Ltd)\.?\s*", re.IGNORECASE)
MIN_ALIAS_LEN: Final = 4


def _aliases(value: str, category: PiiCategory) -> list[str]:
    """Мәтін жасалған кезде нысан кездесетін жазылу нұсқалары.

    Модель жиі «ТОО «Альфа Трейд»» орнына «Альфа Трейд» деп, «#альфатрейд» хэштегін
    немесе тек тегін жазады — әр нұсқа сол токенмен маскаланады.
    """
    aliases: list[str] = []
    if category is PiiCategory.COMPANY:
        inner = _LEGAL_FORM.sub("", value).strip(_QUOTE_OPEN + _QUOTE_CLOSE + " ")
        aliases += [inner, inner.replace(" ", ""), inner.replace(" ", "_"), inner.replace(" ", "-")]
    elif category is PiiCategory.PERSON:
        words = [w.strip(".,") for w in value.split()]
        aliases += [w for w in words if not re.fullmatch(r"[А-ЯЁA-Z]\.?", w)]
        aliases.append("".join(words))
    return [a for a in dict.fromkeys(aliases) if len(a) >= MIN_ALIAS_LEN and a != value]


class AnonymizationSession:
    """Бір сұраныстың in-memory сәйкестік кестесі."""

    def __init__(self) -> None:
        # Кілт — кіші регистрдегі мән: маскалау регистрге тәуелді емес
        # («Альфа Трейд» / «альфа трейд»). Бірнеше кілт (бүркеншік аттар) -> бір токен.
        self._value_to_token: dict[str, str] = {}
        self._token_to_value: dict[str, str] = {}
        self._counters: dict[PiiCategory, int] = {}
        self.llm_detection_used = False

    def register(self, value: str, category: PiiCategory) -> str:
        value = value.strip()
        key = value.lower()
        if key in self._value_to_token:
            return self._value_to_token[key]
        n = self._counters.get(category, 0) + 1
        self._counters[category] = n
        token = f"[{category.value}_{n}]"
        self._value_to_token[key] = token
        self._token_to_value[token] = value
        for alias in _aliases(value, category):
            self._value_to_token.setdefault(alias.lower(), token)
        return token

    def detect(self, text: str) -> None:
        """Регулярлық өрнектер тапқан барлық PII-ді тіркейді.

        Табылғаны жұмыс көшірмесінен қиылады, келесі үлгілер
        табылғанның ішінен үзінділерді таппауы үшін (мысалы, IBAN ішіндегі «картаны»).
        """
        working = text
        for category, pattern in _PATTERNS:
            for match in pattern.finditer(working):
                value = match.group(0)
                self.register(value, category or _classify_12_digits(value))
            working = pattern.sub("\x00", working)

    def anonymize(self, text: str) -> str:
        self.detect(text)
        if not self._value_to_token:
            return text
        # Бір өтім: ұзын мәндер қысқалардан бұрын («ТОО «Альфа Трейд»» «Альфа»-дан бұрын),
        # ал қойылып қойған токенді қысқарақ мән қайта ұстай алмайды.
        values = sorted(self._value_to_token, key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(v) for v in values), re.IGNORECASE)
        return pattern.sub(lambda m: self._value_to_token[m.group(0).lower()], text)

    def deanonymize(self, text: str) -> str:
        if not self._token_to_value:
            return text
        pattern = re.compile("|".join(re.escape(t) for t in self._token_to_value))
        return pattern.sub(lambda m: self._token_to_value[m.group(0)], text)

    def anonymize_json(self, value: JsonValue) -> JsonValue:
        if isinstance(value, str):
            return self.anonymize(value)
        if isinstance(value, list):
            return [self.anonymize_json(v) for v in value]
        if isinstance(value, dict):
            return {k: self.anonymize_json(v) for k, v in value.items()}
        return value

    def deanonymize_json(self, value: JsonValue) -> JsonValue:
        if isinstance(value, str):
            return self.deanonymize(value)
        if isinstance(value, list):
            return [self.deanonymize_json(v) for v in value]
        if isinstance(value, dict):
            return {k: self.deanonymize_json(v) for k, v in value.items()}
        return value

    def leaked(self, text: str) -> int:
        """Мәтінде тіркелген мәндер мен бүркеншік аттардың қаншасы қалды (0 болуы керек)."""
        lowered = text.lower()
        return sum(1 for key in self._value_to_token if key in lowered)

    def leaked_json(self, value: JsonValue) -> int:
        if isinstance(value, str):
            return self.leaked(value)
        if isinstance(value, list):
            return sum(self.leaked_json(v) for v in value)
        if isinstance(value, dict):
            return sum(self.leaked_json(v) for v in value.values())
        return 0

    def report(self, leaked_count: int = 0) -> AnonymizationReport:
        return AnonymizationReport(
            entities_total=len(self._token_to_value),
            by_category=dict(self._counters),
            llm_detection_used=self.llm_detection_used,
            leaked_count=leaked_count,
        )

    def clear(self) -> None:
        self._value_to_token.clear()
        self._token_to_value.clear()
        self._counters.clear()

    def __len__(self) -> int:
        return len(self._token_to_value)


class LocalAnonymizer:
    def __init__(self, llm: LLMClient | None, prompts: PromptLoader) -> None:
        self._llm = llm
        self._prompts = prompts

    async def build_session(self, texts: Iterable[str], *, use_llm: bool = True) -> AnonymizationSession:
        """Бастапқы мәтіндер бойынша сессияны дайындайды: регулярлық өрнектер + (қосымша) жергілікті LLM.

        LLM қолжетімсіз болса, сессия бәрібір регулярлық өрнектер бойынша жасалады —
        бұл дәлдіктің деградациясы, бірақ ағу емес: регулярлық нысандар әрқашан маскаланады.
        """
        session = AnonymizationSession()
        sources = [t for t in texts if t.strip()]
        for text in sources:
            session.detect(text)

        if use_llm and self._llm is not None and sources:
            joined = "\n\n".join(sources)
            messages = [
                ChatMessage(role="system", content=self._prompts.load(PII_PROMPT)),
                ChatMessage(role="user", content=joined),
            ]
            try:
                response = await self._llm.structured(messages, PiiDetectionResult, stage="anonymizing_pii")
            except LLMError as exc:
                log.warning("pii_llm_detection_failed", stage="anonymizing_pii", error_code=exc.code)
            else:
                session.llm_detection_used = True
                for span in response.data.entities:
                    value = span.text.strip()
                    if len(value) >= 2 and value in joined:
                        session.register(value, PiiCategory(span.category.value))
        return session
