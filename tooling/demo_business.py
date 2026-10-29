"""Deterministic demo business data for end-to-end customer-service demos.

This module is deliberately isolated from production integrations. It provides
read-only order/account fixtures and an in-memory refund-ticket workflow so a
demo can show a real tool loop without touching payment providers or customer
data.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from threading import RLock
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DemoOrder:
    order_id: str
    user_id: str
    product_name: str
    amount: float
    currency: str
    status: str
    paid_at: str
    payment_channel: str
    refundable_until: str


class DemoBusinessService:
    """Small in-memory business facade used only by the demo environment."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.demo_mode = os.getenv("HALEX_DEMO_MODE", "true").strip().lower() in {"1", "true", "yes", "on"}
        self._orders: Dict[str, DemoOrder] = {
            "12345": DemoOrder(
                order_id="12345",
                user_id="u1001",
                product_name="lumendesk Support Cloud · Pro 月度订阅",
                amount=89.0,
                currency="AUD",
                status="paid",
                paid_at="2026-10-21T09:14:00+10:00",
                payment_channel="Visa ···· 4242",
                refundable_until="2026-11-04",
            ),
            "54321": DemoOrder(
                order_id="54321",
                user_id="u1001",
                product_name="lumendesk Support Cloud · Team 年度订阅",
                amount=799.0,
                currency="AUD",
                status="paid",
                paid_at="2026-08-02T11:05:00+10:00",
                payment_channel="企业转账",
                refundable_until="2026-08-16",
            ),
        }
        self._refund_tickets: Dict[str, Dict[str, Any]] = {}
        self._next_ticket = 1001

    @staticmethod
    def _normalize_order_id(order_id: str) -> str:
        return str(order_id or "").strip().upper().lstrip("#")

    def lookup_order(self, user_id: str, order_id: str) -> Dict[str, Any]:
        if not self.demo_mode:
            return {"success": False, "demo_data": False, "error": "演示业务数据未启用"}
        normalized_id = self._normalize_order_id(order_id)
        with self._lock:
            order = self._orders.get(normalized_id)
            if order is None or order.user_id != user_id:
                return {
                    "success": False,
                    "found": False,
                    "error": "未找到属于当前用户的演示订单",
                    "order_id": normalized_id,
                }
            ticket = self._refund_tickets.get(normalized_id)
            return {
                "success": True,
                "found": True,
                "demo_data": True,
                "order_id": order.order_id,
                "product_name": order.product_name,
                "amount": order.amount,
                "currency": order.currency,
                "status": order.status,
                "paid_at": order.paid_at,
                "payment_channel": order.payment_channel,
                "refundable_until": order.refundable_until,
                "refund_status": ticket["status"] if ticket else "not_requested",
                "refund_ticket_id": ticket["ticket_id"] if ticket else None,
                "can_request_refund": ticket is None and order.status == "paid",
            }

    def create_refund_ticket(
        self,
        user_id: str,
        order_id: str,
        reason: str,
        confirmed: bool,
    ) -> Dict[str, Any]:
        if not self.demo_mode:
            return {"success": False, "demo_data": False, "error": "演示业务数据未启用"}
        normalized_id = self._normalize_order_id(order_id)
        if not confirmed:
            return {
                "success": False,
                "requires_confirmation": True,
                "message": "创建演示退款工单前需要用户明确确认。",
            }
        with self._lock:
            order = self._orders.get(normalized_id)
            if order is None or order.user_id != user_id:
                return {"success": False, "error": "未找到属于当前用户的演示订单"}
            existing = self._refund_tickets.get(normalized_id)
            if existing:
                return {"success": True, "created": False, **existing}
            ticket = {
                "ticket_id": f"RFD-DEMO-{self._next_ticket}",
                "order_id": normalized_id,
                "status": "pending_review",
                "reason": str(reason or "用户申请退款")[:240],
                "amount": order.amount,
                "currency": order.currency,
                "next_step": "账单团队将在演示队列中核验订单和服务使用情况。",
            }
            self._next_ticket += 1
            self._refund_tickets[normalized_id] = ticket
            return {"success": True, "created": True, "demo_data": True, **ticket}

    def account_security(self, user_id: str) -> Dict[str, Any]:
        if not self.demo_mode:
            return {"success": False, "demo_data": False, "error": "演示业务数据未启用"}
        if user_id != "u1001":
            return {"success": False, "error": "未找到当前用户的演示账户"}
        return {
            "success": True,
            "demo_data": True,
            "account_id": "u1001",
            "risk_status": "clear",
            "mfa_enabled": True,
            "trusted_devices": 2,
            "last_security_event": "2026-10-28T16:20:00+10:00",
            "recommended_action": "修改付款信息前完成重新认证或多因素验证。",
        }


demo_business_service = DemoBusinessService()
