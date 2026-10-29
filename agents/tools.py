"""Agent 工具定义与实现。

所有 Agent 工具集中在这里，编排器只负责：
  1. 根据 Agent 类型暴露工具白名单
  2. 执行 LLM 返回的 tool_use
  3. 将工具结果回传给 LLM

工具本身保持确定性、可测试，并明确区分：
  - 当前请求分析
  - 技术排障建议
  - 账单字段核验
  - 人工升级摘要
  - 共享知识库 RAG

订单查询、退款执行、账单修改等需要真实业务系统授权的动作不在这里伪造。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, TYPE_CHECKING, Union, Tuple

from tooling.demo_business import demo_business_service

if TYPE_CHECKING:
    from agents.agent_orchestrator import Request


AgentToolHandler = Callable[["Request", Dict[str, Any]], Union[Any, Awaitable[Any]]]

GROUNDING_STATUSES = {
    "grounded",
    "insufficient_evidence",
    "conflict",
    "expired",
    "not_applicable",
}


def knowledge_context(req: Request) -> Dict[str, Any]:
    """构造可信的知识检索范围；范围来自请求，不由模型自行猜测。"""
    scope = {
        "product_id": str(getattr(req, "product_id", "") or "").strip(),
        "region": str(getattr(req, "region", "") or "").strip(),
        "channel": str(getattr(req, "channel", "") or "").strip(),
        "tenant_scope": str(getattr(req, "tenant_scope", "") or "").strip(),
    }
    return {"knowledge_filters": scope}


def _grounding_status(results: Any) -> str:
    """从知识库结果中归一化证据状态；旧结果无状态时仅把非空结果视为 grounded。"""
    if not isinstance(results, list) or not results:
        return "insufficient_evidence"
    statuses = {
        str(item.get("grounding_status") or item.get("status") or "").strip().lower()
        for item in results
        if isinstance(item, dict)
    }
    statuses.discard("")
    if "conflict" in statuses:
        return "conflict"
    if "expired" in statuses and statuses <= {"expired"}:
        return "expired"
    if statuses & {"draft", "rejected", "withdrawn", "unpublished"}:
        return "insufficient_evidence"
    if "insufficient_evidence" in statuses:
        return "insufficient_evidence"
    return "grounded"


def _citations(results: Any) -> List[Dict[str, Any]]:
    """把检索片段映射为稳定、可供 Agent 和评测使用的引用结构。"""
    if not isinstance(results, list):
        return []
    citations: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        citations.append({
            "document_id": item.get("document_id", ""),
            "title": item.get("title", ""),
            "source_url": item.get("source_url", ""),
            "policy_version": item.get("policy_version") or item.get("version", ""),
            "effective_from": item.get("effective_from", ""),
            "excerpt": item.get("excerpt") or item.get("content", ""),
            "chunk_id": item.get("chunk_id") or item.get("chunk", ""),
        })
    return citations


@dataclass(frozen=True)
class AgentToolSpec:
    """Agent 可见工具的定义和执行函数。"""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: AgentToolHandler
    allowed_agents: Optional[Tuple[str, ...]] = None
    retry_safe: bool = True


def make_tool(
    name: str,
    description: str,
    properties: Dict[str, Any],
    handler: AgentToolHandler,
    required: Optional[List[str]] = None,
) -> AgentToolSpec:
    """创建带 JSON Schema 的 Agent 工具。"""
    return AgentToolSpec(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
        handler=handler,
    )


def inspect_request_context(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """通用客服工具：返回脱敏后的当前请求快照。"""
    return {
        "intent": req.intent.value if req.intent else None,
        "intent_group": req.intent_group,
        "urgency": req.urgency.name if req.urgency else None,
        "intent_confidence": round(req.intent_confidence, 4),
        "entities": req.entities or {},
        "context_available": bool(req.context),
        "requested_focus": str(args.get("focus", "general"))[:40],
    }


def suggest_required_fields(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """通用客服工具：按业务类型计算下一轮只需询问的字段。"""
    intent = req.intent.value if req.intent else "other"
    fields: List[str] = []
    if intent in {"order_status", "logistics"}:
        fields = ["订单号或下单时间"]
    elif intent in {"account", "account_security"}:
        fields = ["登录方式或账号标识", "问题发生时间"]
    elif intent in {"complaint", "request"}:
        fields = ["事件时间", "期望处理方式"]
    elif intent == "other":
        fields = ["希望解决的具体问题"]
    return {
        "intent": intent,
        "required_fields": fields,
        "known_entities": req.entities or {},
    }


def lookup_error_code(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """技术工具：解释常见错误码的排查方向，不声称读取了服务端日志。"""
    code = str(args.get("error_code", "")).upper().strip()
    mapping = {
        "401": ("认证失败", ["确认 Token/API Key 是否过期", "确认请求时间戳和签名", "确认账号登录状态"]),
        "403": ("权限不足", ["确认账号或套餐权限", "确认资源权限和 IP 白名单"]),
        "404": ("资源或路径不存在", ["确认接口路径和环境", "确认资源标识是否正确"]),
        "500": ("服务端处理异常", ["记录 request_id 和发生时间", "检查依赖服务、参数格式和服务端日志"]),
    }
    meaning, steps = mapping.get(
        code,
        ("暂未识别的错误码", ["补充完整错误信息、发生时间和运行环境"]),
    )
    return {
        "error_code": code,
        "meaning": meaning,
        "next_steps": steps,
        "server_log_checked": False,
    }


def build_diagnostic_plan(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """技术工具：生成低风险排障顺序。"""
    environment = str(args.get("environment", "unknown"))[:80]
    reproduced = bool(args.get("reproduced", False))
    steps = [
        "复现并记录完整错误信息",
        "确认网络、DNS、代理和证书",
        "确认版本、配置和权限",
    ]
    if reproduced:
        steps.append("用最小请求复现并记录 request_id")
    return {
        "environment": environment,
        "reproduced": reproduced,
        "diagnostic_steps": steps,
    }


def check_billing_fields(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """账单工具：检查必要核验字段是否齐全。"""
    fields = {
        "order_id": bool(req.entities.get("order_id")),
        "amount": bool(req.entities.get("amount")),
        "date": bool(req.entities.get("date")),
        "payment_channel": bool(args.get("payment_channel")),
    }
    return {
        "fields": fields,
        "missing_fields": [name for name, present in fields.items() if not present],
        "can_confirm_refund": False,
        "reason": "当前工具只做字段检查，不连接订单或支付系统",
    }


def compare_amounts(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """账单工具：只做用户明确提供金额之间的算术。"""
    try:
        first = float(args["amount_a"])
        second = float(args["amount_b"])
    except (KeyError, TypeError, ValueError):
        return {"success": False, "error": "amount_a 和 amount_b 必须是数字"}
    return {
        "success": True,
        "amount_a": first,
        "amount_b": second,
        "difference": round(first - second, 2),
        "interpretation": "仅表示金额差值，不代表重复扣款或退款结论",
    }


def lookup_demo_order(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """查询隔离的演示订单，不连接真实支付或订单系统。"""
    return demo_business_service.lookup_order(req.user_id, str(args.get("order_id", "")))


def create_demo_refund_ticket(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """在明确确认后创建内存中的演示退款工单。"""
    return demo_business_service.create_refund_ticket(
        req.user_id,
        str(args.get("order_id", "")),
        str(args.get("reason", "用户申请退款")),
        bool(args.get("confirmed", False)),
    )


def lookup_demo_account_security(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """查询隔离的演示账户安全状态，不读取真实账号。"""
    return demo_business_service.account_security(req.user_id)


def create_handoff_summary(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
    """升级工具：生成可交给人工客服的结构化摘要。"""
    return {
        "request_id": req.request_id,
        "reason": str(args.get("reason", "需要人工客服继续核验"))[:120],
        "intent": req.intent.value if req.intent else "unknown",
        "urgency": req.urgency.name if req.urgency else "UNKNOWN",
        "entities": req.entities or {},
        "sensitive_data_required": False,
    }


def build_shared_rag_tools(tool_manager: Any) -> Dict[str, AgentToolSpec]:
    """构建所有 Agent 可共享的 RAG 工具。"""

    async def search_knowledge_base(req: Request, args: Dict[str, Any]) -> Dict[str, Any]:
        query = str(args.get("query") or req.message or "").strip()
        top_k = args.get("top_k", 5)
        if not query:
            return {
                "success": False,
                "error": "query 不能为空",
                "results": [],
                "context": knowledge_context(req),
                "grounding_status": "insufficient_evidence",
                "citations": [],
            }
        if tool_manager is None:
            return {
                "success": False,
                "error": "RAG 工具未初始化",
                "results": [],
                "context": knowledge_context(req),
                "grounding_status": "insufficient_evidence",
                "citations": [],
            }

        result = await tool_manager.search_with_rewrite(
            "knowledge_search",
            query,
            top_k=top_k,
            context=knowledge_context(req),
        )
        if not getattr(result, "success", False):
            return {
                "success": False,
                "query": query,
                "error": getattr(result, "error", "知识库检索失败"),
                "results": [],
                "context": knowledge_context(req),
                "grounding_status": "insufficient_evidence",
                "citations": [],
                "reranked": False,
            }

        return {
            "success": True,
            "query": query,
            "top_k": top_k,
            "results": result.data,
            "context": knowledge_context(req),
            "grounding_status": _grounding_status(result.data),
            "citations": _citations(result.data),
            "cached": bool(getattr(result, "cached", False)),
            "reranked": bool(getattr(result, "reranked", False)),
        }

    return {
        "search_knowledge_base": make_tool(
            "search_knowledge_base",
            "检索知识库并返回最相关的文档片段；可用于通用、技术、账单和升级场景。",
            {
                "query": {"type": "string", "minLength": 1, "maxLength": 2000, "description": "用户问题或检索关键词"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20, "description": "返回结果条数"},
            },
            search_knowledge_base,
            required=["query"],
        )
    }


def general_tools() -> Dict[str, AgentToolSpec]:
    return {
        "inspect_request_context": make_tool(
            "inspect_request_context",
            "查看当前请求的意图、紧急度、实体和上下文可用性；不查询外部业务系统。",
            {"focus": {"type": "string", "description": "希望关注的业务方向"}},
            inspect_request_context,
        ),
        "suggest_required_fields": make_tool(
            "suggest_required_fields",
            "根据当前意图建议下一轮只需向用户补充的字段。",
            {},
            suggest_required_fields,
        ),
        "lookup_account_security": make_tool(
            "lookup_account_security",
            "查询当前用户的演示账户安全状态；不会读取或修改真实账户，也不会索要密码或验证码。",
            {},
            lookup_demo_account_security,
        ),
        "lookup_order": make_tool(
            "lookup_order",
            "查询隔离的 lumendesk 演示订单，返回订单状态、金额和退款资格；不连接真实支付系统。",
            {"order_id": {"type": "string", "minLength": 1, "maxLength": 40, "description": "订单号，例如 12345"}},
            lookup_demo_order,
            required=["order_id"],
        ),
    }


def technical_tools() -> Dict[str, AgentToolSpec]:
    return {
        "lookup_error_code": make_tool(
            "lookup_error_code",
            "解释常见 HTTP 错误码的可能含义和低风险排查方向；不会读取服务端日志。",
            {"error_code": {"type": "string", "description": "例如 401、403、500"}},
            lookup_error_code,
            required=["error_code"],
        ),
        "build_diagnostic_plan": make_tool(
            "build_diagnostic_plan",
            "根据运行环境和是否可复现生成排障顺序，不执行修改配置等操作。",
            {
                "environment": {"type": "string", "description": "App、浏览器、服务端或 Docker 等"},
                "reproduced": {"type": "boolean", "description": "问题是否可以稳定复现"},
            },
            build_diagnostic_plan,
            required=["environment", "reproduced"],
        ),
    }


def billing_tools() -> Dict[str, AgentToolSpec]:
    return {
        "check_billing_fields": make_tool(
            "check_billing_fields",
            "检查账单核验字段是否齐全；不连接订单、支付或退款系统。",
            {"payment_channel": {"type": "string", "description": "支付渠道，例如微信、支付宝、银行卡"}},
            check_billing_fields,
        ),
        "compare_amounts": make_tool(
            "compare_amounts",
            "计算用户明确提供的两笔金额差值；不判断是否重复扣款，也不执行退款。",
            {
                "amount_a": {"type": "number", "description": "第一笔金额"},
                "amount_b": {"type": "number", "description": "第二笔金额"},
            },
            compare_amounts,
            required=["amount_a", "amount_b"],
        ),
        "lookup_order": make_tool(
            "lookup_order",
            "查询隔离的 lumendesk 演示订单，返回订单状态、金额和退款资格；不连接真实支付系统。",
            {"order_id": {"type": "string", "minLength": 1, "maxLength": 40, "description": "订单号，例如 12345"}},
            lookup_demo_order,
            required=["order_id"],
        ),
        "create_refund_ticket": AgentToolSpec(
            name="create_refund_ticket",
            description="在用户明确确认后创建隔离的演示退款工单；不会执行真实退款。",
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "minLength": 1, "maxLength": 40},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 240},
                    "confirmed": {"type": "boolean"},
                },
                "required": ["order_id", "reason", "confirmed"],
                "additionalProperties": False,
            },
            handler=create_demo_refund_ticket,
            retry_safe=False,
        ),
        "lookup_account_security": make_tool(
            "lookup_account_security",
            "查询当前用户的演示账户安全状态；不会读取或修改真实账户，也不会索要密码或验证码。",
            {},
            lookup_demo_account_security,
        ),
    }


def escalation_tools() -> Dict[str, AgentToolSpec]:
    return {
        "create_handoff_summary": make_tool(
            "create_handoff_summary",
            "生成交给人工客服的结构化交接摘要，不会创建真实工单。",
            {"reason": {"type": "string", "description": "需要升级的原因"}},
            create_handoff_summary,
        ),
    }
