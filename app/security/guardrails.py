"""Guardrails — Sprint 6.

기능
- ``mask_pii``: 한국 주민번호(13자리), 카드번호(16자리), 계좌번호 추정 패턴, 이메일을 마스킹.
- ``classify_input``: prompt-injection / 범위외(out-of-scope) / 정상.
- ``sanitize_text``: 위험 토큰 제거 후 길이 제한.

본 모듈은 기존 ``query_planner._classify_intent`` 와 별개로 동작하며,
입력단(API) 에서 1차 차단을, 플래너에서 2차 분류를 수행하는 이중 방어다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal

PII_RESIDENT_RE = re.compile(r"\b\d{6}[- ]?\d{7}\b")
PII_CARD_RE = re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b")
PII_BANK_RE = re.compile(r"\b\d{2,4}-\d{2,4}-\d{2,7}\b")
PII_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")

PROMPT_INJECTION_HINTS: tuple[str, ...] = (
    "이전 시스템 지시",
    "이전 지시",
    "system prompt",
    "ignore previous",
    "ignore the above",
    "disregard",
    "비밀번호",
    "비공개 영업 비밀",
    "내부 지시",
    "탈옥",
    "jailbreak",
    "developer mode",
)

OUT_OF_SCOPE_HINTS: tuple[str, ...] = (
    "점심", "메뉴", "레시피", "농담", "노래",
    "비방", "비난", "공격적", "악성", "악담",
)

InputClass = Literal["safe", "out_of_scope", "prompt_injection"]


@dataclass(frozen=True)
class GuardrailVerdict:
    classification: InputClass
    reasons: tuple[str, ...] = ()

    @property
    def is_safe(self) -> bool:
        return self.classification == "safe"


def mask_pii(text: str) -> str:
    if not text:
        return ""
    masked = PII_RESIDENT_RE.sub("***-RRN-***", text)
    masked = PII_CARD_RE.sub("***-CARD-***", masked)
    masked = PII_BANK_RE.sub("***-BANK-***", masked)
    masked = PII_EMAIL_RE.sub("***-EMAIL-***", masked)
    return masked


def _matches_any(text: str, hints: Iterable[str]) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for hint in hints:
        if hint in text or hint.lower() in lowered:
            found.append(hint)
    return found


def classify_input(text: str) -> GuardrailVerdict:
    if not text:
        return GuardrailVerdict("safe")
    injection_hits = _matches_any(text, PROMPT_INJECTION_HINTS)
    if injection_hits:
        return GuardrailVerdict("prompt_injection", tuple(injection_hits))
    pii_hits: list[str] = []
    if PII_RESIDENT_RE.search(text):
        pii_hits.append("resident_number")
    if PII_CARD_RE.search(text):
        pii_hits.append("card_number")
    if PII_BANK_RE.search(text):
        pii_hits.append("bank_number")
    if pii_hits:
        return GuardrailVerdict("out_of_scope", tuple(["pii_detected", *pii_hits]))
    oos_hits = _matches_any(text, OUT_OF_SCOPE_HINTS)
    if oos_hits:
        return GuardrailVerdict("out_of_scope", tuple(oos_hits))
    return GuardrailVerdict("safe")


def sanitize_text(text: str, *, max_length: int = 2000) -> str:
    """입력을 PII 마스킹 + 길이 제한.

    LLM 호출 직전 이 함수를 거치도록 합쳐 두면 PII 가 외부로 새는 것을 막는다.
    """
    if not text:
        return ""
    masked = mask_pii(text)
    if len(masked) > max_length:
        masked = masked[:max_length] + "…(truncated)"
    return masked


__all__ = [
    "GuardrailVerdict",
    "InputClass",
    "PROMPT_INJECTION_HINTS",
    "OUT_OF_SCOPE_HINTS",
    "classify_input",
    "mask_pii",
    "sanitize_text",
]
