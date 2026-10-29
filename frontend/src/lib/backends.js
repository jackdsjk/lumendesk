import { pollEvaluation } from './evaluationJobs.js'

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true'
const DEMO_QUOTA_LIMIT = 12
const demoTraces = new Map()
const demoState = { pendingOrderId: '', refundTicketId: '' }

const demoDocuments = [
  {
    document_id: 'halex-demo-billing',
    title: 'lumendesk Support Cloud 演示退款与账单规则',
    content: '演示环境中，购买后 14 个自然日内可提交退款申请；账单团队会核对订单、服务使用情况和付款状态后决定是否批准。',
    chunk_count: 3,
    approval_status: 'approved',
    publication_status: 'published',
    product_id: 'halex-support-cloud',
    region: 'AU',
    channel: 'web',
    tenant_scope: 'demo',
    version: 'demo-v1',
    effective_from: '2026-10-29'
  },
  {
    document_id: 'halex-demo-security',
    title: 'lumendesk Support Cloud 演示账户安全处理',
    content: '修改付款信息、重置密码等敏感操作需要重新认证或多因素验证。客服不会索要密码、一次性验证码或完整支付凭据。',
    chunk_count: 2,
    approval_status: 'approved',
    publication_status: 'published',
    product_id: 'halex-support-cloud',
    region: 'AU',
    channel: 'web',
    tenant_scope: 'demo',
    version: 'demo-v1',
    effective_from: '2026-10-29'
  },
  {
    document_id: 'halex-demo-boundaries',
    title: 'lumendesk Support Cloud 演示客服边界与升级',
    content: '演示客服可以解释已发布的产品和账单资料，但不会承诺真实退款、法律结论或未核验的业务事实。',
    chunk_count: 2,
    approval_status: 'approved',
    publication_status: 'published',
    product_id: 'halex-support-cloud',
    region: 'AU',
    channel: 'web',
    tenant_scope: 'demo',
    version: 'demo-v1',
    effective_from: '2026-10-29'
  }
]

export function isDemoMode() {
  return DEMO_MODE
}

function demoQuotaKey() {
  return `halex.demo.quota:${new Date().toISOString().slice(0, 10)}`
}

function consumeDemoQuota() {
  const key = demoQuotaKey()
  const used = Number(sessionStorage.getItem(key) || 0)
  if (used >= DEMO_QUOTA_LIMIT) {
    throw new Error(`GitHub Pages 演示额度已用完（每日 ${DEMO_QUOTA_LIMIT} 次），请明天再试或连接 lumendesk API。`)
  }
  sessionStorage.setItem(key, String(used + 1))
  return DEMO_QUOTA_LIMIT - used - 1
}

function demoId(prefix) {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return `${prefix}-${crypto.randomUUID()}`
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function demoOrder(orderId) {
  return orderId === '54321'
    ? { orderId: '54321', product: 'lumendesk Support Cloud · Team 年度订阅', amount: 799, currency: 'AUD', payment: '企业转账', refundable: false, deadline: '2026-08-16' }
    : { orderId: '12345', product: 'lumendesk Support Cloud · Pro 月度订阅', amount: 89, currency: 'AUD', payment: 'Visa ···· 4242', refundable: true, deadline: '2026-11-04' }
}

function extractOrderId(message) {
  const match = String(message || '').match(/(?:#|订单(?:号|编号)?\s*)?(12345|54321)\b/)
  return match?.[1] || demoState.pendingOrderId || '12345'
}

function demoTrace(toolCalls) {
  return {
    tools_used: toolCalls.map(call => call.tool_name),
    tool_calls: toolCalls
  }
}

function demoChat(settings, message, remaining) {
  const text = String(message || '')
  const requestId = demoId('demo-request')
  const conversationId = settings.conversationId || demoId('demo-conversation')
  const orderId = extractOrderId(text)
  const order = demoOrder(orderId)
  const isSecurity = /付款信息|账户安全|安全验证|多因素|MFA|验证方式/i.test(text)
  const isRefund = /退款|退费|退钱/.test(text)
  const isConfirmed = /确认|提交|发起/.test(text) && isRefund
  const lookupCall = {
    tool_name: 'lookup_order',
    success: true,
    input: { order_id: orderId },
    result_preview: {
      success: true,
      found: true,
      demo_data: true,
      order_id: order.orderId,
      product_name: order.product,
      amount: order.amount,
      currency: order.currency,
      status: 'paid',
      refund_status: demoState.refundTicketId ? 'pending_review' : 'not_requested',
      can_request_refund: order.refundable
    }
  }
  let response
  let intent = 'order_status'
  let agent = 'general'
  let calls = []
  if (isSecurity) {
    intent = 'account'
    agent = 'billing'
    calls = [{
      tool_name: 'lookup_account_security',
      success: true,
      input: {},
      result_preview: { success: true, demo_data: true, risk_status: 'clear', mfa_enabled: true, trusted_devices: 2, recommended_action: '修改付款信息前完成重新认证或多因素验证。' }
    }]
    response = '这是 lumendesk GitHub 演示账户：当前风险状态正常，已开启 MFA，并有 2 台受信任设备。修改付款信息前请完成重新认证或多因素验证。演示客服不会索要密码、验证码或完整支付凭据。'
  } else if (isRefund && isConfirmed) {
    intent = 'refund'
    agent = 'billing'
    demoState.pendingOrderId = order.orderId
    if (!demoState.refundTicketId) demoState.refundTicketId = 'RFD-DEMO-1001'
    calls = [lookupCall, {
      tool_name: 'create_refund_ticket',
      success: true,
      input: { order_id: order.orderId, reason: '服务不符合预期', confirmed: true },
      result_preview: { success: true, created: true, demo_data: true, ticket_id: demoState.refundTicketId, order_id: order.orderId, status: 'pending_review', amount: order.amount, currency: order.currency }
    }]
    response = `演示退款工单已创建：${demoState.refundTicketId}。订单 ${order.orderId} 金额为 ${order.amount} ${order.currency}，当前状态为待审核。请注意：这是 GitHub Pages 的模拟工单，不会执行真实退款。`
  } else if (isRefund) {
    intent = 'refund'
    agent = 'billing'
    demoState.pendingOrderId = order.orderId
    calls = [lookupCall]
    response = `已查到演示订单 #${order.orderId}：${order.product}，金额 ${order.amount} ${order.currency}，状态为已支付。${order.refundable ? `当前仍在退款窗口内（截止 ${order.deadline}）。如果要继续创建模拟退款工单，请明确回复“确认提交退款申请”。` : '当前已超出演示退款窗口，建议转人工审核。'}`
  } else if (/订单|金额|状态|支付|订阅/.test(text)) {
    calls = [lookupCall]
    response = `已查到演示订单 #${order.orderId}：\n\n- 产品：${order.product}\n- 金额：${order.amount} ${order.currency}\n- 状态：已支付（paid）\n- 支付渠道：${order.payment}\n- 退款截止日期：${order.deadline}\n\n这是 GitHub Pages 演示数据，不连接真实订单系统。`
  } else if (/登录|报错|错误|故障|排查/.test(text)) {
    intent = 'technical_login'
    agent = 'technical'
    calls = [{ tool_name: 'lookup_error_code', success: true, input: { error_code: '401' }, result_preview: { error_code: '401', meaning: '认证失败', server_log_checked: false } }]
    response = '演示技术支持建议先确认登录状态和令牌有效期，再重新登录。此页面不会读取真实日志或要求你提交完整 Token。'
  } else {
    intent = 'other'
    calls = [{ tool_name: 'search_knowledge_base', success: true, input: { query: text, top_k: 5 }, result_preview: { grounding_status: 'grounded', citations: 3 } }]
    response = '这是 lumendesk 的 GitHub Pages 演示模式。你可以试试：查询订单 #12345、申请退款、修改付款信息时需要怎样验证，或询问登录故障。'
  }
  demoTraces.set(requestId, demoTrace(calls))
  return normalizeChatResponse('python', {
    request_id: requestId,
    conv_id: conversationId,
    response,
    intent,
    intent_group: agent === 'billing' ? 'billing' : agent === 'technical' ? 'technical' : 'query',
    agent_type: agent,
    agent_types: [agent],
    primary_agent: agent,
    routing_confidence: 1,
    knowledge_used: true,
    grounding_status: 'grounded',
    citations: demoDocuments.slice(0, 2).map(document => ({ document_id: document.document_id, title: document.title, policy_version: document.version, source_url: '' })),
    knowledge_scope: { product_id: 'halex-support-cloud', region: 'AU', channel: 'web', tenant_scope: 'demo' },
    latency_ms: 120,
    demo_mode: true,
    demo_quota_remaining: remaining
  })
}
const PYTHON_BACKEND = {
  id: 'python',
  label: 'Python',
  baseUrl: runtimeConfig().pythonApiUrl || import.meta.env.VITE_PYTHON_API_URL || '/api/python',
  port: '8000'
}

export function createInitialSettings() {
  const saved = readSettings()
  return {
    pythonToken: '',
    backend: 'python',
    userId: saved.userId || 'u1001',
    conversationId: saved.conversationId || '',
    endpoints: {
      python: saved.endpoints?.python || PYTHON_BACKEND.baseUrl
    }
  }
}

export function saveSettings(settings) {
  localStorage.setItem('halex.frontend.settings', JSON.stringify({ ...settings, pythonToken: undefined }))
}

export function backendMeta(type, settings) {
  return {
    ...PYTHON_BACKEND,
    baseUrl: normalizeBaseUrl(settings.endpoints.python || PYTHON_BACKEND.baseUrl)
  }
}

export async function requestHealth(type, settings) {
  if (DEMO_MODE) return { status: 'ok', demo_mode: true, message: 'GitHub Pages 静态演示模式' }
  return requestFor(type, settings, '/health')
}

export async function requestMonitor(type, settings) {
  if (DEMO_MODE) return { agent_stats: {}, tool_stats: {}, active_alerts: [], suggestions: [], demo_mode: true }
  return requestFor(type, settings, '/monitor')
}

export async function requestSkills(type, settings) {
  if (DEMO_MODE) return { count: 3, skills: [{ name: 'general_customer_service', description: '通用客服接待与分流', content_chars: 420 }, { name: 'billing_support', description: '账单与退款边界', content_chars: 510 }, { name: 'technical_support', description: '技术排障与安全边界', content_chars: 480 }], errors: [], demo_mode: true }
  return requestFor(type, settings, '/skills')
}

export async function reloadSkills(type, settings) {
  if (DEMO_MODE) return requestSkills(type, settings)
  return requestFor(type, settings, '/skills/reload', { method: 'POST' })
}

export async function requestKnowledgeStats(type, settings) {
  if (DEMO_MODE) return { total_chunks: 7, demo_mode: true }
  return requestFor(type, settings, '/knowledge/stats')
}

export async function requestKnowledgeDocuments(type, settings, limit = 100) {
  if (DEMO_MODE) return { documents: demoDocuments.slice(0, limit), total: demoDocuments.length, demo_mode: true }
  const params = new URLSearchParams({
    include_unpublished: 'true',
    limit: String(limit)
  })
  return requestFor(type, settings, `/knowledge/documents?${params}`)
}

export async function runEvaluation(type, settings, body = null, options = {}) {
  if (DEMO_MODE) return { status: 'completed', total: 4, passed: 4, valid_total: 4, pass_rate: 1, evaluation_errors: 0, regressions: [], demo_mode: true }
  const taskKey = `halex.eval:${type}:${backendMeta(type, settings).baseUrl}:${settings.userId}`
  const savedJob = sessionStorage.getItem(taskKey)
  const initial = savedJob ? {job_id: savedJob, status: 'queued', completed: 0, total: 0} : await requestFor(type, settings, '/eval/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  })
  if (!initial.job_id) return initial
  sessionStorage.setItem(taskKey, initial.job_id)
  try {
    const result = await pollEvaluation(initial, jobId => requestFor(type, settings,
      `/eval/jobs/${encodeURIComponent(jobId)}`), options)
    if (result) sessionStorage.removeItem(taskKey)
    return result
  } catch (error) {
    if (error.terminal || error.status === 404) sessionStorage.removeItem(taskKey)
    throw error
  }
}

export async function requestSearch(type, settings, query, topK = 5) {
  if (DEMO_MODE) {
    const normalized = String(query || '').toLowerCase()
    const results = demoDocuments.filter(document => `${document.title} ${document.content}`.toLowerCase().includes(normalized.includes('安全') || normalized.includes('付款') ? '安全' : normalized.includes('退款') || normalized.includes('账单') ? '退款' : 'lumendesk'))
      .slice(0, topK)
      .map((document, index) => ({ ...document, id: document.document_id, score: Number((0.92 - index * 0.08).toFixed(2)) }))
    return { results, grounding_status: results.length ? 'grounded' : 'insufficient_evidence', citations: results, knowledge_scope: { product_id: 'halex-support-cloud', region: 'AU', channel: 'web', tenant_scope: 'demo' }, demo_mode: true }
  }
  const params = new URLSearchParams({
    query,
    top_k: String(topK),
    product_id: 'halex-support-cloud',
    region: 'AU',
    channel: 'web',
    tenant_scope: 'global'
  })
  return requestFor(type, settings, `/search?${params}`, { method: 'POST' })
}

export async function requestChat(type, settings, message) {
  if (DEMO_MODE) return demoChat(settings, message, consumeDemoQuota())
  const meta = backendMeta(type, settings)
  const payload = buildChatPayload(type, settings, message)
  const attemptKey = JSON.stringify([type, meta.baseUrl, settings.userId, settings.conversationId, message])
  if (!chatAttempts.has(attemptKey)) {
    if (chatAttempts.size > 100) chatAttempts.clear()
    chatAttempts.set(attemptKey, crypto.randomUUID())
  }
  payload.client_request_id = chatAttempts.get(attemptKey)
  const raw = await requestFor(type, settings, '/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  chatAttempts.delete(attemptKey)
  return normalizeChatResponse(type, raw)
}

export async function requestToolTrace(type, settings, requestId) {
  if (DEMO_MODE) return { request_id: requestId, found: demoTraces.has(requestId), trace: demoTraces.get(requestId) || { tools_used: [], tool_calls: [] }, demo_mode: true }
  if (!requestId) return null
  const raw = await requestFor(type, settings, `/trace/tool/${encodeURIComponent(requestId)}`)
  return normalizeToolTraceResponse(raw)
}

export async function addKnowledge(type, settings, documents) {
  if (DEMO_MODE) return { success: true, demo_mode: true, added: documents?.length || 0, message: 'GitHub Pages 演示模式不会持久化知识文档。' }
  return requestFor(type, settings, '/knowledge/add', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ documents })
  })
}

export async function uploadKnowledge(type, settings, file) {
  if (DEMO_MODE) return { success: true, demo_mode: true, filename: file?.name || '', message: 'GitHub Pages 演示模式不会持久化上传文件。' }
  const form = new FormData()
  form.append('file', file)
  return requestFor(type, settings, '/knowledge/upload', {
    method: 'POST',
    body: form
  })
}

function buildChatPayload(type, settings, message) {
  return {
    message,
    user_id: settings.userId || 'anonymous',
    conv_id: settings.conversationId || undefined,
    product_id: 'halex-support-cloud',
    region: 'AU',
    channel: 'web',
    tenant_scope: 'global'
  }
}

function normalizeChatResponse(type, raw) {
  return {
    backend: type,
    conversationId: raw.conversation_id || raw.conversationId || raw.conv_id || '',
    requestId: raw.request_id || raw.requestId || '',
    response: raw.response || '',
    intent: raw.intent || 'other',
    intentGroup: raw.intent_group || raw.intentGroup || 'other',
    agentType: raw.agent_type || raw.agentType || '',
    agentTypes: raw.agent_types || raw.agentTypes || [],
    primaryAgent: raw.primary_agent || raw.primaryAgent || '',
    supportingAgents: raw.supporting_agents || raw.supportingAgents || [],
    routingReason: raw.routing_reason || raw.routingReason || '',
    routingConfidence: Number(raw.routing_confidence ?? raw.routingConfidence ?? 0),
    entities: raw.entities || {},
    intentConfidence: Number(raw.intent_confidence ?? raw.intentConfidence ?? 0),
    intentSourceScores: raw.intent_source_scores || raw.intentSourceScores || {},
    escalated: Boolean(raw.escalated),
    latencyMs: Number(raw.latency_ms ?? raw.latencyMs ?? 0),
    knowledgeUsed: Boolean(raw.knowledge_used ?? raw.knowledgeUsed),
    groundingStatus: raw.grounding_status || raw.groundingStatus || 'not_applicable',
    citations: Array.isArray(raw.citations) ? raw.citations : [],
    knowledgeScope: raw.knowledge_scope || raw.knowledgeScope || {
      product_id: 'halex-support-cloud',
      region: 'AU',
      channel: 'web',
      tenant_scope: 'global'
    },
    verified: raw.verified,
    grounded: raw.grounded,
    raw
  }
}

function normalizeToolTraceResponse(raw) {
  const trace = raw?.trace || {}
  return {
    requestId: raw?.request_id || raw?.requestId || '',
    found: Boolean(raw?.found),
    trace: {
      ...trace,
      toolsUsed: trace.tools_used || trace.toolsUsed || [],
      toolCalls: trace.tool_calls || trace.toolCalls || []
    },
    raw
  }
}

const chatAttempts = new Map()
async function requestFor(type, settings, path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (settings.pythonToken) headers.set('Authorization', `Bearer ${settings.pythonToken}`)
  return requestJson(backendMeta(type, settings).baseUrl, path, { ...options, headers,
    signal: options.signal || AbortSignal.timeout(path === '/chat' ? 55000 : 20000) })
}

async function requestJson(baseUrl, path, options = {}) {
  const url = `${normalizeBaseUrl(baseUrl)}${path}`
  const response = await fetch(url, options)
  const text = await response.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!response.ok) {
    const detail = typeof data === 'string' ? data : JSON.stringify(data)
    const error = new Error(`${response.status} ${response.statusText}: ${detail}`)
    error.status = response.status
    throw error
  }
  return data
}

function normalizeBaseUrl(value) {
  return String(value || '').replace(/\/+$/, '')
}

function readSettings() {
  try {
    const current = localStorage.getItem('halex.frontend.settings')
    const legacy = localStorage.getItem('lumendesk.frontend.settings')
    const value = current || legacy || '{}'
    if (!current && legacy) localStorage.setItem('halex.frontend.settings', legacy)
    return JSON.parse(value)
  } catch {
    return {}
  }
}

function runtimeConfig() {
  if (typeof window === 'undefined') return {}
  return window.__HALEX_CONFIG__ || window.__LUMENDESK_CONFIG__ || {}
}
