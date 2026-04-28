from __future__ import annotations

import pytest

from app.retrieval.cypher_safety import (
    ALLOWED_LABELS,
    UnsafeCypherError,
    assert_safe,
)


def test_safe_simple_match_return():
    safe = assert_safe(
        "MATCH (c:Company {name: $name})-[:HAS_REPORT]->(r:FinancialReport) RETURN c, r",
        {"name": "카카오"},
    )
    assert safe.cypher.startswith("MATCH")
    assert safe.params["name"] == "카카오"


def test_blocks_create_keyword():
    with pytest.raises(UnsafeCypherError) as ex:
        assert_safe("CREATE (c:Company {name: 'x'}) RETURN c")
    assert "CREATE" in str(ex.value)


def test_blocks_set_keyword():
    with pytest.raises(UnsafeCypherError):
        assert_safe("MATCH (c:Company {name: $n}) SET c.name = 'y' RETURN c")


def test_blocks_unknown_label():
    with pytest.raises(UnsafeCypherError):
        assert_safe("MATCH (x:Person) RETURN x")


def test_blocks_unknown_relationship():
    with pytest.raises(UnsafeCypherError):
        assert_safe("MATCH (c:Company)-[:DEFRAUDED]->(d:Disclosure) RETURN c, d")


def test_blocks_multiple_statements():
    with pytest.raises(UnsafeCypherError):
        assert_safe("MATCH (c:Company) RETURN c; MATCH (d:Disclosure) RETURN d")


def test_requires_match_and_return():
    with pytest.raises(UnsafeCypherError):
        assert_safe("WITH 1 AS x")


def test_blocks_apoc_writes():
    with pytest.raises(UnsafeCypherError):
        assert_safe("MATCH (c:Company) CALL apoc.periodic.iterate('MATCH ()','RETURN 1',{}) RETURN c")


def test_strips_comments():
    # /* DELETE */ 가 주석이라 차단되지 않아야 함
    safe = assert_safe(
        "/* DELETE this is just a comment */ MATCH (c:Company {name: $n}) RETURN c",
        {"n": "카카오"},
    )
    assert safe.cypher.startswith("/*") or safe.cypher.startswith("MATCH") or "/*" in safe.cypher


def test_allowed_labels_match_schema_doc():
    expected = {"Company", "Subsidiary", "FinancialReport", "Disclosure"}
    assert expected == set(ALLOWED_LABELS)
