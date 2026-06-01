from __future__ import annotations

import json
import logging
from typing import Any, Dict

from app.agents.edges import MAX_REFLEXIONS
from app.agents.llm_structured import extract_finance_metrics, extract_risk_points
from app.agents.streaming import active_thread, put_token
from app.observability import start_span
from app.retrieval.query_planner import plan_query
from app.retrieval.query_router import hybrid_retrieve, hybrid_retrieve_multi
from app.retrieval.real_clients import extract_companies as _extract_companies_node
from app.retrieval.multi_entity import is_comparison_query as _is_comparison
from app.schemas import QueryPlan
from app.security.guardrails import classify_input, sanitize_text
from app.state import GraphState, STATE_SCHEMA_VERSION

logger = logging.getLogger(__name__)

_EVAL_PASS_THRESHOLD = float(7.0)
_EMA_LR = 0.3


def _evidence_ids(retrieved_context: Dict[str, Any]) -> list:
    return [str(ev.get("evidence_id", "")) for ev in retrieved_context.get("evidence", []) if ev.get("evidence_id")]


async def input_guardrails_node(state: GraphState) -> Dict[str, Any]:
    """Input safety validation: PII masking, prompt injection, scope check."""
    raw_query = state.get("user_query", "")
    verdict = classify_input(raw_query)
    sanitized = sanitize_text(raw_query)

    if not verdict.is_safe:
        block_reason = verdict.classification
        block_msg = {
            "prompt_injection": "Prompt injection detected. Request blocked.",
            "out_of_scope": "This system handles financial/disclosure analysis only.",
        }.get(block_reason, "Request blocked by safety policy.")

        return {
            "guardrails_verdict": {"classification": verdict.classification, "reasons": list(verdict.reasons)},
            "blocked": True,
            "block_reason": block_reason,
            "sanitized_query": sanitized,
            "messages": [{"role": "guardrails", "content": block_msg}],
            "next_node": "generate_final_report",
        }

    return {
        "guardrails_verdict": {"classification": "safe", "reasons": []},
        "blocked": False,
        "sanitized_query": sanitized,
        "user_query": sanitized,
        "next_node": "intent_classifier",
    }


async def evaluation_node(state: GraphState) -> Dict[str, Any]:
    """Output quality evaluation node (LLM-as-Judge)."""
    from app.config import settings
    from app.llm.providers.base import LLMRequest
    from app.llm.router import get_router

    query = state.get("user_query", "")
    finance = state.get("finance_metrics", {})
    risk = state.get("risk_points", [])
    answer_text = str(finance.get("insight", "")) + " " + "; ".join(risk[:3])
    sources_summary = "evidence={}, mode={}".format(
        len(state.get("evidence", [])),
        state.get("retrieved_context", {}).get("mode", "unknown")
    )

    if not settings.has_real_llm:
        critic = state.get("critic_report", {})
        disagreement = float(critic.get("disagreement_score", state.get("disagreement_score", 0.5)) or 0.5)
        has_evidence = bool(state.get("evidence"))
        base = 8.0 if has_evidence else 5.0
        total = max(0.0, base - disagreement * 4.0)
        passed = total >= _EVAL_PASS_THRESHOLD
        return {
            "eval_score": {"accuracy": total / 3, "completeness": total / 3, "conciseness": 2.5, "citation": 0.5 if has_evidence else 0.0, "total": total},
            "eval_passed": passed,
            "eval_feedback": "heuristic eval (no LLM)",
            "next_node": "generate_final_report" if passed else "reflector",
        }

    try:
        from app.prompts import get_registry
        prompt = get_registry().render(
            "evaluation_judge",
            query=query,
            answer=answer_text[:500],
            sources_summary=sources_summary,
        )
    except Exception:
        prompt = (
            "Query: {}\nAnswer: {}\nSources: {}\n"
            'Evaluate JSON: {{"accuracy":0-3,"completeness":0-3,"conciseness":0-3,"citation":0-1,"total":sum,"feedback":"..."}}'
        ).format(query, answer_text[:300], sources_summary)

    router = get_router()
    try:
        resp = await router.invoke("evaluator", LLMRequest(prompt=prompt, temperature=0.0, json_mode=True))
        data = json.loads(resp.text.strip().strip("```json").strip("```").strip())
        total = float(data.get("total", 5.0))
        passed = total >= _EVAL_PASS_THRESHOLD
        return {
            "eval_score": data,
            "eval_passed": passed,
            "eval_feedback": str(data.get("feedback", "")),
            "next_node": "generate_final_report" if passed else "reflector",
        }
    except Exception as exc:
        logger.warning("evaluation LLM failed (%s) -- passing", exc)
        return {
            "eval_score": {"total": 7.0, "note": "eval_error"},
            "eval_passed": True,
            "eval_feedback": "",
            "next_node": "generate_final_report",
        }


async def intent_classifier_node(state: GraphState) -> Dict[str, Any]:
    """Classify query intent and determine routing."""
    plan = await plan_query(state["user_query"])
    next_node = "retrieve_context" if plan.overall_intent != "out_of_scope" else "generate_final_report"
    return {
        "intent": plan.overall_intent,
        "query_plan": plan.model_dump(),
        "schema_version": STATE_SCHEMA_VERSION,
        "next_node": next_node,
    }


async def retrieve_context_node(state: GraphState) -> Dict[str, Any]:
    company = state.get("target_company")
    year = state.get("target_year")
    plan_dict = state.get("query_plan")
    plan = QueryPlan.model_validate(plan_dict) if plan_dict else None
    user_query = state["user_query"]

    # Multi-entity path: 2+ companies detected -> parallel retrieval
    companies = _extract_companies_node(user_query)
    use_multi = (
        len(companies) >= 2
        and _is_comparison(user_query)
    )

    async with start_span(
        "retrieve_context",
        attrs={
            "company": company or "",
            "year": year or 0,
            "intent": (plan.overall_intent if plan else "unknown"),
            "multi_entity": use_multi,
        },
    ):
        if use_multi:
            context = await hybrid_retrieve_multi(user_query, companies=companies, plan=plan)
        else:
            context = await hybrid_retrieve(user_query, company=company, year=year, plan=plan)

    return {
        "retrieved_context": context,
        "evidence": list(context.get("evidence", [])),
        "next_node": "finance_analyst",
    }


async def finance_analyst_node(state: GraphState) -> Dict[str, Any]:
    context = state.get("retrieved_context", {})
    payload = await extract_finance_metrics(context)
    payload.setdefault("evidence_ids", _evidence_ids(context))
    return {
        "finance_metrics": payload,
        "messages": [{"role": "finance_analyst", "content": str(payload)}],
        "next_node": "risk_compliance",
    }


async def risk_compliance_node(state: GraphState) -> Dict[str, Any]:
    context = state.get("retrieved_context", {})
    risks = await extract_risk_points(context)
    return {
        "risk_points": risks,
        "messages": [{"role": "risk_compliance", "content": "; ".join(risks)}],
        "next_node": "critic",
    }


async def critic_node(state: GraphState) -> Dict[str, Any]:
    """Score citation gaps, generalities, and contradictions in analyst outputs."""
    finance_metrics = state.get("finance_metrics", {}) or {}
    risk_points = state.get("risk_points", []) or []
    analysis_context = state.get("retrieved_context", {}).get("analysis_context", {})
    data_quality = analysis_context.get("data_quality", {})
    flags = list(data_quality.get("flags", []))
    has_evidence = bool(state.get("evidence"))

    missing_citations = []
    if not finance_metrics.get("evidence_ids"):
        missing_citations.append("finance_metrics.evidence_ids")
    if not risk_points:
        missing_citations.append("risk_points")

    contradictions = []
    debt = finance_metrics.get("debt_ratio")
    insight = str(finance_metrics.get("insight", ""))
    if isinstance(debt, (int, float)) and debt and debt < 150 and "상승" in insight:
        contradictions.append("debt_ratio < 150 but insight says rising")
    if isinstance(debt, (int, float)) and debt and debt > 200 and "안정" in insight:
        contradictions.append("debt_ratio > 200 but insight says stable")

    score = 0.0
    if missing_citations:
        score += 0.4
    if not has_evidence:
        score += 0.2
    if contradictions:
        score += 0.4
    if "financial_parse_failed" in flags or "financial_context_missing" in flags:
        score += 0.1
    if not finance_metrics.get("has_sufficient_data") and not risk_points:
        score += 0.1
    score = min(1.0, score)

    request_re_retrieval = bool(
        score >= 0.5 and state.get("reflexion_count", 0) < MAX_REFLEXIONS and not has_evidence
    )

    critic_report = {
        "disagreement_score": score,
        "missing_citations": missing_citations,
        "contradictions": contradictions,
        "request_re_retrieval": request_re_retrieval,
        "notes": ", ".join(flags[:3]) if flags else "ok",
    }

    next_node = "reflector" if request_re_retrieval else "orchestrator"
    return {
        "critic_report": critic_report,
        "disagreement_score": score,
        "messages": [{"role": "critic", "content": str(critic_report)}],
        "next_node": next_node,
    }


def _update_retrieval_weights_ema(
    current_weights: Dict[str, Any],
    disagreement_score: float,
    has_evidence: bool,
) -> Dict[str, Any]:
    """Update retrieval weights using EMA based on reflection feedback."""
    authority = float(current_weights.get("authority_weight", 0.5))
    diversity = float(current_weights.get("diversity_bonus", 0.1))
    recency = float(current_weights.get("recency_weight", 0.5))

    target_authority = min(0.9, authority + _EMA_LR * disagreement_score * 0.5)
    new_authority = authority + _EMA_LR * (target_authority - authority)

    diversity_signal = 0.2 if not has_evidence else 0.0
    new_diversity = min(0.5, diversity + _EMA_LR * diversity_signal)

    return {
        "authority_weight": round(new_authority, 3),
        "diversity_bonus": round(new_diversity, 3),
        "recency_weight": recency,
    }


async def reflector_node(state: GraphState) -> Dict[str, Any]:
    """Refine query plan and update retrieval weights via EMA when critic requests re-retrieval."""
    count = state.get("reflexion_count", 0) + 1
    if count > MAX_REFLEXIONS:
        return {
            "reflexion_count": count,
            "messages": [{"role": "reflector", "content": "MAX_REFLEXIONS reached -- routing to orchestrator"}],
            "next_node": "orchestrator",
        }

    current_weights = state.get("retrieval_weights") or {
        "authority_weight": 0.5,
        "diversity_bonus": 0.1,
        "recency_weight": 0.5,
    }
    disagreement = float(state.get("disagreement_score", 0.5) or 0.5)
    has_evidence = bool(state.get("evidence"))
    new_weights = _update_retrieval_weights_ema(current_weights, disagreement, has_evidence)

    quality_score = max(0.0, 1.0 - disagreement)
    boost_factor = 1.0 + (disagreement * 0.3)

    plan_dict = state.get("query_plan") or {}
    try:
        plan = QueryPlan.model_validate(plan_dict)
        boosted = []
        for sq in plan.sub_queries:
            boosted_sq = sq.model_copy(update={"weight": min(1.5, sq.weight * boost_factor)})
            boosted.append(boosted_sq)
        plan = plan.model_copy(update={"sub_queries": boosted})
        new_plan = plan.model_dump()
    except Exception:
        new_plan = plan_dict

    return {
        "reflexion_count": count,
        "query_plan": new_plan,
        "retrieval_weights": new_weights,
        "reflection_quality_score": quality_score,
        "messages": [
            {
                "role": "reflector",
                "content": (
                    "EMA weight update: authority={:.2f}, diversity={:.2f} | "
                    "boost={:.2f}x -> retrieve_context"
                ).format(new_weights["authority_weight"], new_weights["diversity_bonus"], boost_factor),
            }
        ],
        "next_node": "retrieve_context",
    }


def _build_orchestrator_decision(state: GraphState) -> str:
    finance_metrics = state.get("finance_metrics", {})
    finance_insight = str(finance_metrics.get("insight", "")).strip()
    risk_points = [str(point).strip() for point in state.get("risk_points", []) if str(point).strip()]
    analysis_context = state.get("retrieved_context", {}).get("analysis_context", {})
    data_quality = analysis_context.get("data_quality", {})
    flags = [str(flag) for flag in data_quality.get("flags", []) if str(flag)]
    mode = data_quality.get("mode", state.get("retrieved_context", {}).get("mode", "fallback"))

    summary_parts = []
    if finance_insight:
        summary_parts.append(finance_insight)
    if risk_points and risk_points != ["중대 공시 리스크 미탐지"]:
        summary_parts.append("주요 리스크는 {}.입니다.".format(", ".join(risk_points[:2])))
    if flags:
        summary_parts.append("데이터 품질 제약({}) 때문에 결론은 보수적으로 해석해야 합니다.".format(", ".join(flags[:3])))
    elif mode in {"partial_real", "fallback"}:
        summary_parts.append("`{}` 모드 기반입니다.".format(mode))

    return " ".join(summary_parts) or "재무 및 공시 정보가 충분하지 않아 추가 확인이 필요합니다."


async def orchestrator_node(state: GraphState) -> Dict[str, Any]:
    turn = state.get("turn_count", 0) + 1
    score = float(state.get("disagreement_score", 0.0) or 0.0)

    has_fin = bool(state.get("finance_metrics"))
    has_risk = bool(state.get("risk_points"))
    consensus = has_fin and has_risk and score <= 0.2
    decision = (
        _build_orchestrator_decision(state)
        if consensus
        else "재무 또는 리스크 정보가 충분하지 않아 추가 확인이 필요합니다. (disagreement={:.2f})".format(score)
    )

    thread_id = state.get("trace_id") or active_thread()
    if thread_id:
        for token in decision.split(" "):
            if token:
                put_token(thread_id, "orchestrator", token + " ")

    return {
        "turn_count": turn,
        "consensus_reached": consensus,
        "messages": [{"role": "orchestrator", "content": decision}],
        "next_node": "evaluation",
    }


async def generate_final_report_node(state: GraphState) -> Dict[str, Any]:
    block_reason = state.get("block_reason")
    if state.get("blocked") and block_reason:
        notice = "blocked: {}".format(block_reason)
    elif state.get("intent") == "out_of_scope":
        notice = "out_of_scope"
    elif not state.get("consensus_reached"):
        notice = "max_turns_exceeded"
    else:
        notice = "ok"

    summary = {
        "finance": state.get("finance_metrics", {}),
        "risk": state.get("risk_points", []),
        "consensus_reached": state.get("consensus_reached", False),
        "turn_count": state.get("turn_count", 0),
        "intent": state.get("intent"),
        "evidence_count": len(state.get("evidence", []) or []),
        "disagreement_score": state.get("disagreement_score"),
        "eval_score": state.get("eval_score"),
        "system_notice": notice,
    }
    return {"messages": [{"role": "final", "content": str(summary)}]}
