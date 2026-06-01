"""RAGAS gate module — real RAGAS library when available, heuristic fallback otherwise.

Usage:
    from eval.ragas_gate import evaluate_ragas, GATE_THRESHOLDS

    results = await evaluate_ragas(samples)   # list of RagasSample
    passed, report = check_gate(results)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# CI gate thresholds (heuristic / no-LLM mode).
# Without a real LLM the ragas_like_* scores are near-zero by construction,
# so heuristic mode only gates on pass_rate (keyword/citation checks).
GATE_THRESHOLDS = {
    "pass_rate": 0.75,
}

# Real RAGAS thresholds (used with --ragas flag, LLM required)
RAGAS_THRESHOLDS = {
    "faithfulness": 0.75,
    "answer_relevance": 0.65,
    "answer_correctness": 0.65,
    "context_recall": 0.70,
}


@dataclass
class RagasSample:
    """One evaluation sample."""
    question: str
    answer: str
    contexts: list[str]
    ground_truth: str = ""


@dataclass
class RagasResult:
    faithfulness: float
    answer_relevance: float
    answer_correctness: float
    context_recall: float
    source: str = "heuristic"
    raw: dict[str, Any] = field(default_factory=dict)


def _heuristic_faithfulness(answer: str, contexts: list[str]) -> float:
    """Fraction of answer tokens (len>=4) that appear in context."""
    if not answer or not contexts:
        return 0.0
    ctx = " ".join(contexts).lower()
    tokens = [t for t in answer.lower().split() if len(t) >= 4]
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in ctx) / len(tokens)


def _heuristic_answer_relevance(answer: str, question: str) -> float:
    """Fraction of question tokens (len>=3) that appear in answer."""
    if not answer or not question:
        return 0.0
    ans = answer.lower()
    tokens = [t for t in question.lower().split() if len(t) >= 3]
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in ans) / len(tokens)


def _heuristic_answer_correctness(answer: str, ground_truth: str) -> float:
    """Token overlap F1 between answer and ground_truth."""
    if not answer or not ground_truth:
        return 0.0
    a_tokens = set(t for t in answer.lower().split() if len(t) >= 3)
    g_tokens = set(t for t in ground_truth.lower().split() if len(t) >= 3)
    if not a_tokens or not g_tokens:
        return 0.0
    intersection = a_tokens & g_tokens
    precision = len(intersection) / len(a_tokens)
    recall = len(intersection) / len(g_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _heuristic_context_recall(contexts: list[str], ground_truth: str) -> float:
    """Fraction of ground_truth tokens that appear in context."""
    if not contexts or not ground_truth:
        return 0.0
    ctx = " ".join(contexts).lower()
    tokens = [t for t in ground_truth.lower().split() if len(t) >= 3]
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in ctx) / len(tokens)


def evaluate_heuristic(samples: list[RagasSample]) -> list[RagasResult]:
    """Run heuristic evaluation. Zero external deps."""
    results = []
    for s in samples:
        results.append(RagasResult(
            faithfulness=_heuristic_faithfulness(s.answer, s.contexts),
            answer_relevance=_heuristic_answer_relevance(s.answer, s.question),
            answer_correctness=_heuristic_answer_correctness(s.answer, s.ground_truth),
            context_recall=_heuristic_context_recall(s.contexts, s.ground_truth),
            source="heuristic",
        ))
    return results


def _stub_missing_langchain_modules() -> None:
    """Stub only the specific langchain_community submodules that newer
    langchain-community versions removed (e.g. chat_models.vertexai).
    langchain-community itself must be installed: pip install langchain-community
    """
    import sys
    import types

    # These submodules were removed in langchain-community >= 0.1.x
    # RAGAS still references them for optional Vertex AI support.
    missing = [
        ("langchain_community.chat_models.vertexai", ["ChatVertexAI"]),
        ("langchain_community.llms.vertexai", ["VertexAI"]),
        ("langchain_community.embeddings.vertexai", ["VertexAIEmbeddings"]),
    ]
    for mod_name, class_names in missing:
        try:
            __import__(mod_name)
        except ImportError:
            if mod_name not in sys.modules:
                mod = types.ModuleType(mod_name)
                mod.__path__ = []
                mod.__package__ = mod_name
                sys.modules[mod_name] = mod
            stub = sys.modules[mod_name]
            for cls_name in class_names:
                if not hasattr(stub, cls_name):
                    setattr(stub, cls_name, type(cls_name, (), {}))


def _configure_ragas_llm():
    """Return (llm, embeddings) tuple for RAGAS using app LLM settings.

    Normalizes LLM_BASE_URL (strips /chat/completions suffix that ChatOpenAI
    appends itself).  Uses native google-genai for embeddings.
    """
    import os
    from app.config import settings  # type: ignore

    api_key = settings.llm_api_key or os.getenv("LLM_API_KEY", "")
    model = settings.llm_model or "gemini-2.0-flash"

    # Normalize base_url: ChatOpenAI appends /chat/completions itself,
    # so strip it from LLM_BASE_URL if already present.
    raw_url = (settings.llm_base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
    for _suffix in ("/chat/completions", "/completions"):
        if raw_url.endswith(_suffix):
            raw_url = raw_url[: -len(_suffix)].rstrip("/")
            break
    base_url = raw_url  # e.g. https://generativelanguage.googleapis.com/v1beta/openai

    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY not set. Set it or use heuristic mode (omit --ragas)."
        )

    from ragas.llms import LangchainLLMWrapper  # type: ignore
    from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore
    from langchain_openai import ChatOpenAI  # type: ignore
    from langchain_google_genai import GoogleGenerativeAIEmbeddings  # type: ignore

    chat_kwargs: dict = {"model": model, "api_key": api_key}
    if base_url:
        chat_kwargs["base_url"] = base_url
    llm = LangchainLLMWrapper(ChatOpenAI(**chat_kwargs))

    # Use native Gemini embeddings (Gemini OpenAI-compat has no embeddings endpoint)
    emb = LangchainEmbeddingsWrapper(
        GoogleGenerativeAIEmbeddings(
            model="models/gemini-embedding-001", google_api_key=api_key
        )
    )
    return llm, emb


async def evaluate_ragas_real(samples: list[RagasSample]) -> list[RagasResult]:
    """Run real RAGAS evaluation (requires ragas + OPENAI_API_KEY).

    Requires:
        pip install ragas langchain-openai datasets

    Falls back to heuristic if ragas is not installed or LLM is not configured.
    """
    try:
        import importlib
        if importlib.util.find_spec("ragas") is None:
            raise ImportError("ragas not installed -- run: pip install ragas langchain-openai datasets")

        # Stub out optional LangChain community modules before RAGAS loads them
        _stub_missing_langchain_modules()

        from ragas import evaluate as ragas_evaluate  # type: ignore
        from ragas.metrics import (  # type: ignore
            answer_correctness,
            answer_relevancy,
            context_recall,
            faithfulness,
        )
        from datasets import Dataset  # type: ignore

        # Configure LLM. RAGAS reads OPENAI_API_KEY/OPENAI_BASE_URL from env
        # for ALL internal LLM calls, so we must set env vars to our LLM endpoint
        # (Gemini OpenAI-compat), not just pass llm= to evaluate().
        import os as _os
        from app.config import settings as _settings
        _api_key = _settings.llm_api_key or _os.getenv("OPENAI_API_KEY", "")
        _base_url = _settings.llm_base_url or ""
        if not _api_key:
            raise RuntimeError(
                "LLM_API_KEY not set -- cannot run real RAGAS. "
                "Set LLM_API_KEY env var or use heuristic mode (omit --ragas)."
            )
        # Temporarily redirect RAGAS to our LLM endpoint
        _orig_key = _os.environ.get("OPENAI_API_KEY")
        _orig_url = _os.environ.get("OPENAI_BASE_URL")
        _os.environ["OPENAI_API_KEY"] = _api_key
        if _base_url:
            _os.environ["OPENAI_BASE_URL"] = _base_url
        try:
            llm, emb = _configure_ragas_llm()
            metrics_list = [faithfulness, answer_relevancy, context_recall, answer_correctness]
            ragas_data = {
                "question": [s.question for s in samples],
                "answer": [s.answer for s in samples],
                "contexts": [s.contexts if s.contexts else [""] for s in samples],
                "ground_truth": [s.ground_truth for s in samples],
            }
            ds = Dataset.from_dict(ragas_data)
            import inspect as _inspect
            _eval_sig = _inspect.signature(ragas_evaluate)
            _eval_kw: dict = {"dataset": ds, "metrics": metrics_list}
            if "llm" in _eval_sig.parameters:
                _eval_kw["llm"] = llm
            if "embeddings" in _eval_sig.parameters:
                _eval_kw["embeddings"] = emb
            result = ragas_evaluate(**_eval_kw)
        finally:
            # Always restore original env vars
            if _orig_key is None:
                _os.environ.pop("OPENAI_API_KEY", None)
            else:
                _os.environ["OPENAI_API_KEY"] = _orig_key
            if _orig_url is None:
                _os.environ.pop("OPENAI_BASE_URL", None)
            elif _base_url:
                _os.environ["OPENAI_BASE_URL"] = _orig_url
        df = result.to_pandas()

        ragas_results = []
        for _, row in df.iterrows():
            ragas_results.append(RagasResult(
                faithfulness=float(row.get("faithfulness", 0) or 0),
                answer_relevance=float(row.get("answer_relevancy", 0) or 0),
                answer_correctness=float(row.get("answer_correctness", 0) or 0),
                context_recall=float(row.get("context_recall", 0) or 0),
                source="ragas",
                raw=row.to_dict(),
            ))
        return ragas_results
    except Exception as exc:
        logger.warning("Real RAGAS failed (%s) -- heuristic fallback", exc)
        return evaluate_heuristic(samples)


def aggregate(results: list[RagasResult]) -> dict[str, float]:
    """Compute mean metrics across all samples."""
    if not results:
        return {k: 0.0 for k in ["faithfulness", "answer_relevance", "answer_correctness", "context_recall"]}

    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    return {
        "faithfulness": _mean([r.faithfulness for r in results]),
        "answer_relevance": _mean([r.answer_relevance for r in results]),
        "answer_correctness": _mean([r.answer_correctness for r in results]),
        "context_recall": _mean([r.context_recall for r in results]),
        "source": results[0].source if results else "unknown",
    }


def check_gate(metrics: dict, *, real_mode: bool = False) -> tuple[bool, dict]:
    """Check if metrics pass the CI gate thresholds.

    Heuristic mode (--gate only): gates on pass_rate >= 0.75.
    Real RAGAS mode (--ragas): gates on faithfulness/answer_relevance/etc.

    Returns (passed: bool, report: dict).
    """
    thresholds = RAGAS_THRESHOLDS if real_mode else GATE_THRESHOLDS
    failures = []
    checks = {}
    for key, floor in thresholds.items():
        actual = float(metrics.get(key, 0.0))
        ok = actual >= floor
        checks[key] = {"actual": round(actual, 4), "floor": floor, "passed": ok}
        if not ok:
            failures.append(f"{key}={actual:.3f} < {floor}")

    overall = len(failures) == 0
    report = {
        "passed": overall,
        "mode": "ragas" if real_mode else "heuristic",
        "checks": checks,
        "failures": failures,
    }
    return overall, report


__all__ = [
    "RagasSample",
    "RagasResult",
    "evaluate_heuristic",
    "evaluate_ragas_real",
    "aggregate",
    "check_gate",
    "GATE_THRESHOLDS",
    "RAGAS_THRESHOLDS",
]
