"""Prompt Registry — YAML 기반 프롬프트 관리.

설계 원칙
- prompts/*.yaml 파일을 한 번 로드하고 LRU 캐시로 재사용.
- Jinja2 미설치 시 str.format_map() 으로 graceful fallback.
- 환경변수 PROMPT_OVERRIDE_DIR 로 런타임 오버라이드 디렉터리 지정 가능.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PROMPTS_DIR = Path(__file__).parent / "templates"
_JINJA2_AVAILABLE: bool | None = None


def _jinja2_available() -> bool:
    global _JINJA2_AVAILABLE
    if _JINJA2_AVAILABLE is None:
        try:
            import jinja2  # noqa: F401
            _JINJA2_AVAILABLE = True
        except ImportError:
            _JINJA2_AVAILABLE = False
    return _JINJA2_AVAILABLE


def _render_simple(template: str, variables: dict[str, Any]) -> str:
    """Jinja2 미가용 시 {{ var }} 형태를 단순 치환."""
    def replacer(m: re.Match) -> str:  # type: ignore[type-arg]
        key = m.group(1).strip()
        val = variables.get(key)
        if val is None:
            return m.group(0)
        return str(val)
    return re.sub(r"\{\{(.+?)\}\}", replacer, template)


class PromptRegistry:
    """YAML 파일에서 프롬프트 템플릿을 로드하고 렌더링."""

    def __init__(self, prompts_dir: Path | str | None = None) -> None:
        base = Path(prompts_dir) if prompts_dir else _DEFAULT_PROMPTS_DIR
        # 환경변수 오버라이드
        override = os.getenv("PROMPT_OVERRIDE_DIR", "").strip()
        self._dirs: list[Path] = []
        if override:
            self._dirs.append(Path(override))
        self._dirs.append(base)
        self._cache: dict[str, str] = {}

    def _load_raw(self, name: str) -> str:
        """이름으로 템플릿 원문(YAML body 이후 텍스트) 반환."""
        if name in self._cache:
            return self._cache[name]

        for d in self._dirs:
            for ext in (".yaml", ".yml", ".j2", ".txt"):
                candidate = d / f"{name}{ext}"
                if candidate.exists():
                    raw = candidate.read_text(encoding="utf-8")
                    # YAML front-matter(--- ... ---) 제거
                    raw = re.sub(r"^---\n.*?---\n", "", raw, flags=re.DOTALL)
                    self._cache[name] = raw.strip()
                    logger.debug("Prompt '%s' loaded from %s", name, candidate)
                    return self._cache[name]

        raise FileNotFoundError(
            f"Prompt template '{name}' not found in {[str(d) for d in self._dirs]}"
        )

    def render(self, name: str, **variables: Any) -> str:
        """템플릿 이름과 변수를 받아 최종 프롬프트 문자열을 반환."""
        raw = self._load_raw(name)
        if _jinja2_available():
            from jinja2 import Environment, StrictUndefined

            env = Environment(
                undefined=StrictUndefined,
                trim_blocks=True,
                lstrip_blocks=True,
            )
            try:
                return env.from_string(raw).render(**variables)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Jinja2 render error for '%s': %s — falling back", name, exc)
        return _render_simple(raw, variables)

    def invalidate(self, name: str | None = None) -> None:
        """캐시 무효화 (배포 없이 프롬프트 교체 시 사용)."""
        if name:
            self._cache.pop(name, None)
        else:
            self._cache.clear()


@lru_cache(maxsize=1)
def get_registry() -> PromptRegistry:
    """앱 전역 싱글톤 레지스트리."""
    return PromptRegistry()


__all__ = ["PromptRegistry", "get_registry"]
