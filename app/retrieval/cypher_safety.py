"""Cypher Safety Guard — Sprint 2.

목적
- Sprint 3 에서 LLM 이 합성하는 Cypher 의 read-only 보장.
- DML 키워드(CREATE/MERGE/DELETE/SET/REMOVE/DROP/CALL APOC.UPDATES 등) 차단.
- 라벨/관계 화이트리스트(`Company`, `Subsidiary`, `FinancialReport`, `Disclosure`,
  `OWNS`, `HAS_REPORT`, `INVOLVED_IN`) 외 사용 차단.

본 모듈은 외부 의존성 없이 ``str`` 만 다룬다. 실제 Neo4j 호출은 별도 책임.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED_LABELS = frozenset({"Company", "Subsidiary", "FinancialReport", "Disclosure"})
ALLOWED_REL_TYPES = frozenset({"OWNS", "HAS_REPORT", "INVOLVED_IN"})

_DML_TOKENS = (
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "DROP",
    "FOREACH",
    "LOAD CSV",
)
_FORBIDDEN_PROCEDURES = (
    "CALL APOC.PERIODIC",
    "CALL APOC.LOAD",
    "CALL APOC.EXPORT",
    "CALL DBMS",
    "CALL APOC.CYPHER.RUN",
    "CALL APOC.CYPHER.RUNWRITE",
)
_REQUIRED_TOKENS = ("MATCH", "RETURN")
_RELATIONSHIP_BLOCK_RE = re.compile(r"\[[^\[\]]*\]")
_LABEL_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
_REL_TYPE_RE = re.compile(r"\[\s*[\w?]*\s*:\s*([A-Z_][A-Z0-9_]*(?:\s*\|\s*[A-Z_][A-Z0-9_]*)*)")


def _extract_labels(cypher: str) -> set[str]:
    """노드 라벨만 추출. 관계 타입(`[...:TYPE]`)은 별도 추출 대상."""
    no_rel_blocks = _RELATIONSHIP_BLOCK_RE.sub(" ", cypher)
    return set(_LABEL_RE.findall(no_rel_blocks))


def _extract_rel_types(cypher: str) -> set[str]:
    raw = _REL_TYPE_RE.findall(cypher)
    out: set[str] = set()
    for token in raw:
        for piece in token.split("|"):
            piece = piece.strip()
            if piece:
                out.add(piece)
    return out


class UnsafeCypherError(ValueError):
    pass


@dataclass(frozen=True)
class SafeCypher:
    cypher: str
    params: dict


def _strip_comments(cypher: str) -> str:
    no_block = re.sub(r"/\*.*?\*/", " ", cypher, flags=re.DOTALL)
    no_line = re.sub(r"//[^\n]*", " ", no_block)
    return no_line


def _normalize(cypher: str) -> str:
    return _strip_comments(cypher).strip().rstrip(";").upper()


def assert_safe(cypher: str, params: dict | None = None) -> SafeCypher:
    """안전성 검사를 통과한 Cypher 만 ``SafeCypher`` 로 감싼다.

    검사 실패 시 ``UnsafeCypherError`` 를 발생시킨다.
    """
    if not cypher or not cypher.strip():
        raise UnsafeCypherError("empty cypher")

    if ";" in cypher.strip().rstrip(";"):
        raise UnsafeCypherError("multiple statements are not allowed")

    upper = _normalize(cypher)

    for token in _DML_TOKENS:
        if re.search(rf"\b{re.escape(token)}\b", upper):
            raise UnsafeCypherError(f"DML keyword '{token}' is not allowed")

    for proc in _FORBIDDEN_PROCEDURES:
        if proc in upper:
            raise UnsafeCypherError(f"forbidden procedure: {proc}")

    if not all(token in upper for token in _REQUIRED_TOKENS):
        raise UnsafeCypherError("query must contain MATCH and RETURN")

    cleaned = _strip_comments(cypher)
    used_labels = _extract_labels(cleaned)
    if used_labels and not used_labels.issubset(ALLOWED_LABELS):
        unknown = used_labels - ALLOWED_LABELS
        raise UnsafeCypherError(f"unknown label(s): {sorted(unknown)}")

    used_rels = _extract_rel_types(cleaned)
    if used_rels and not used_rels.issubset(ALLOWED_REL_TYPES):
        unknown = used_rels - ALLOWED_REL_TYPES
        raise UnsafeCypherError(f"unknown relationship(s): {sorted(unknown)}")

    return SafeCypher(cypher=cypher.strip().rstrip(";"), params=dict(params or {}))


__all__ = [
    "SafeCypher",
    "UnsafeCypherError",
    "assert_safe",
    "ALLOWED_LABELS",
    "ALLOWED_REL_TYPES",
]
