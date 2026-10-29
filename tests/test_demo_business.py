from agents.tools import (
    billing_tools,
    lookup_demo_account_security,
    lookup_demo_order,
    create_demo_refund_ticket,
)
from agents.agent_orchestrator import Request
from core.intent_recognizer import IntentCategory, UrgencyLevel


def make_request(user_id: str = "u1001") -> Request:
    return Request(
        message="查询订单 #12345",
        user_id=user_id,
        conv_id="demo-business-test",
        intent=IntentCategory.REFUND,
        intent_group="billing",
        urgency=UrgencyLevel.LOW,
        intent_confidence=1.0,
        entities={"order_id": ["12345"]},
    )


def test_lookup_demo_order_returns_safe_fixture():
    result = lookup_demo_order(make_request(), {"order_id": "#12345"})

    assert result["success"] is True
    assert result["demo_data"] is True
    assert result["order_id"] == "12345"
    assert result["amount"] == 89.0
    assert result["currency"] == "AUD"


def test_refund_ticket_requires_explicit_confirmation_and_is_idempotent():
    request = make_request()
    spec = billing_tools()["create_refund_ticket"]

    rejected = create_demo_refund_ticket(
        request,
        {"order_id": "12345", "reason": "服务不符合预期", "confirmed": False},
    )
    assert rejected["success"] is False
    assert rejected["requires_confirmation"] is True

    created = create_demo_refund_ticket(
        request,
        {"order_id": "12345", "reason": "服务不符合预期", "confirmed": True},
    )
    assert created["success"] is True
    assert created["created"] is True
    assert created["ticket_id"] == "RFD-DEMO-1001"
    assert spec.retry_safe is False

    repeated = create_demo_refund_ticket(
        request,
        {"order_id": "12345", "reason": "重复提交", "confirmed": True},
    )
    assert repeated["success"] is True
    assert repeated["created"] is False
    assert repeated["ticket_id"] == "RFD-DEMO-1001"


def test_account_security_is_demo_only():
    result = lookup_demo_account_security(make_request(), {})

    assert result["success"] is True
    assert result["demo_data"] is True
    assert result["mfa_enabled"] is True
    assert result["risk_status"] == "clear"
