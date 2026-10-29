import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents.agent_orchestrator import (
    AgentType,
    Request,
    _grounding_guard,
)
from evaluation.evaluator import EndToEndEvaluator, QualityScores


def test_grounding_guard_is_conservative_for_missing_or_conflicting_evidence():
    missing, missing_escalates = _grounding_guard("我会帮你处理。", "insufficient_evidence")
    conflict, conflict_escalates = _grounding_guard("这是当前政策。", "conflict")

    assert missing_escalates is True
    assert "资料不足" in missing
    assert conflict_escalates is True
    assert "政策存在冲突" in conflict


def test_evaluator_checks_grounding_citations_forbidden_claims_and_scope():
    class Orchestrator:
        async def run(self, req):
            assert req.product_id == "lumendesk-pro"
            assert req.region == "AU"
            return SimpleNamespace(
                response="当前资料不足，请转人工核验。",
                agent_type=AgentType.GENERAL,
                intent=None,
                status="success",
                tools_used=[],
                escalated=True,
                grounding_status="insufficient_evidence",
                citations=[],
            )

    evaluator = EndToEndEvaluator.__new__(EndToEndEvaluator)
    evaluator._orchestrator = Orchestrator()
    evaluator._judge = SimpleNamespace(
        judge=AsyncMock(return_value=QualityScores(1, 1, 1, 1))
    )

    results = asyncio.run(evaluator._evaluate_dialog_case({
        "question": "这个产品能退款吗？",
        "product_id": "lumendesk-pro",
        "region": "AU",
        "channel": "web",
        "expected_grounding_status": "insufficient_evidence",
        "expected_escalation": True,
        "required_citations": [],
        "forbidden_claims": ["退款已成功"],
    }, 0))

    assert results[0].passed is True
    assert results[0].metadata["deterministic_checks"] == {
        "grounding_status": True,
        "escalation": True,
        "forbidden_claims": True,
    }
    assert results[0].metadata["knowledge_scope"] == {
        "product_id": "lumendesk-pro",
        "region": "AU",
        "channel": "web",
        "tenant_scope": "",
    }
