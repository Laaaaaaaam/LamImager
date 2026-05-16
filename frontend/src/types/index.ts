export interface ApiVendor {
  id: string
  name: string
  base_url: string
  api_key_masked: string
  is_active: boolean
  model_count: number
  created_at: string
  updated_at: string
}

export interface ApiVendorCreate {
  name: string
  base_url: string
  api_key: string
  is_active?: boolean
}

export interface ApiVendorUpdate {
  name?: string
  base_url?: string
  api_key?: string
  is_active?: boolean
}

export interface ApiProvider {
  id: string
  nickname: string
  base_url: string
  model_id: string
  vendor_id: string | null
  vendor_name: string
  api_key_masked: string
  provider_type: 'image_gen' | 'llm' | 'web_search'
  billing_type: 'per_call' | 'per_token'
  unit_price: number
  currency: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ApiProviderCreate {
  nickname: string
  base_url?: string
  model_id: string
  vendor_id?: string | null
  api_key?: string
  provider_type: 'image_gen' | 'llm' | 'web_search'
  billing_type?: 'per_call' | 'per_token'
  unit_price?: number
  currency?: string
  is_active?: boolean
}

export interface ApiProviderUpdate {
  nickname?: string
  base_url?: string | null
  model_id?: string
  vendor_id?: string | null
  api_key?: string
  provider_type?: 'image_gen' | 'llm' | 'web_search'
  billing_type?: 'per_call' | 'per_token'
  unit_price?: number
  currency?: string
  is_active?: boolean
}

export interface Skill {
  id: string
  name: string
  description: string
  prompt_template: string
  parameters: Record<string, unknown>
  is_builtin: boolean
  strategy: string
  steps: Record<string, unknown>[]
  strategy_hint: string
  planning_bias: Record<string, unknown>
  constraints: Record<string, unknown>
  prompt_bias: Record<string, unknown>
  created_at: string
}

export interface Rule {
  id: string
  name: string
  rule_type: 'default_params' | 'filter' | 'workflow'
  config: Record<string, unknown>
  is_active: boolean
  priority: number
  created_at: string
}

export interface BillingSummary {
  today: number
  month: number
  total: number
  currency: string
}

export interface BillingRecord {
  id: string
  session_id: string | null
  provider_id: string | null
  billing_type: string
  tokens_in: number
  tokens_out: number
  cost: number
  currency: string
  detail: Record<string, unknown>
  created_at: string
}

export interface BillingBreakdown {
  by_provider: Array<{
    provider_id: string
    nickname: string
    cost: number
    tokens: number
  }>
  by_type: Array<{
    type: string
    label: string
    cost: number
    tokens: number
    count: number
  }>
}

export interface ReferenceImage {
  id: string
  name: string
  file_path: string
  file_type: string
  file_size: number
  thumbnail: string
  is_global: boolean
  strength: number
  crop_config: Record<string, unknown>
  created_at: string
}

export interface PromptOptimizeResult {
  original: string
  optimized: string
  direction: string
}

export interface SessionInfo {
  id: string
  title: string
  status: 'idle' | 'generating' | 'optimizing' | 'planning' | 'error'
  created_at: string
  updated_at: string
  message_count: number
  cost: number
  tokens: number
}

export interface TaskHandle {
  sessionId: string
  type: 'generate' | 'optimize' | 'plan'
  status: 'running' | 'done' | 'error'
  progress: number
  total: number
  abortController: AbortController | null
  taskType?: string
  strategy?: string
}

export interface TaskUpdateEvent {
  session_id: string
  status: string
  progress: number
  total: number
  message: string
  task_type?: string
  strategy?: string
}

export interface Message {
  id: string
  session_id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  message_type: 'text' | 'image' | 'plan' | 'optimization' | 'skill' | 'error' | 'agent' | 'agent_timeline'
  metadata: Record<string, unknown>
  created_at: string
}

export interface GenerateRequest {
  session_id: string
  prompt: string
  negative_prompt?: string
  image_count?: number
  image_size?: string
  skill_ids?: string[]
  optimize_directions?: string[]
  custom_optimize_instruction?: string
  reference_images?: string[]
  reference_labels?: { index: number; source: string; name: string }[]
  context_messages?: { role: string; content: string; image_urls?: string[] }[]
  plan_strategy?: string
  agent_mode?: boolean
  agent_tools?: string[]
  agent_plan_strategy?: string
}

export interface PlanStep {
  prompt: string
  negative_prompt: string
  description: string
  image_count?: number
  image_size?: string
  /** @deprecated */
  reference_step_indices?: number[]
  checkpoint?: {
    enabled: boolean
    message: string
    auto_continue_seconds?: number
  }
}

export interface TemplateVariable {
  key: string
  type: 'string' | 'select' | 'number'
  label: string
  default: string | any[]
  options?: string[]
  required?: boolean
}

export interface PlanTemplate {
  id: string
  name: string
  description: string
  strategy: 'parallel' | 'iterative' | 'radiate'
  steps: PlanStep[]
  variables: TemplateVariable[]
  is_builtin: boolean
  created_at: string
  updated_at: string
}

export interface DefaultModelsConfig {
  default_optimize_provider_id: string | null
  default_image_provider_id: string | null
  default_plan_provider_id: string | null
  default_image_width: number
  default_image_height: number
  max_concurrent: number
}

export interface AgentStepEvent {
  type: 'tool_call' | 'tool_result'
  name: string
  args?: Record<string, unknown>
  content?: string
  meta?: Record<string, unknown>
}

export interface LamEventPayload {
  type: string
  session_id: string
  content?: string
  name?: string
  args?: Record<string, unknown>
  meta?: Record<string, unknown>
  error?: string
  reason?: string
  retry_count?: number
  tokens_in?: number
  tokens_out?: number
  cost?: number
  partial_output?: string
  tool_name?: string
  message?: string
  preview?: string
  status?: string
  progress?: number
  total?: number
  node?: string
  detail?: Record<string, unknown>
  artifacts?: Array<{ type: string; url: string }>
  step?: { description: string }
}

export interface LamEvent {
  event_id: string
  timestamp: number
  source_product: string
  target_product: string | null
  event_type: string
  correlation_id: string
  payload: LamEventPayload
}

export interface AgentStreamState {
  sessionId: string
  status: 'connecting' | 'thinking' | 'tool_running' | 'paused' | 'done' | 'error' | 'cancelled'
  content: string
  steps: AgentStreamStep[]
  cost: number | null
  startedAt: number | null
}

export interface AgentStreamStep {
  id: string
  type: 'tool_call' | 'tool_result' | 'checkpoint' | 'plan' | 'node_progress'
  name: string
  status: 'pending' | 'running' | 'done' | 'error' | 'step_done'
  group: 'key' | 'internal'
  args?: Record<string, unknown>
  content?: string
  meta?: Record<string, unknown>
}

export interface ContextImage {
  url: string
  source: 'upload' | 'context' | 'refine'
  name: string
  preview?: string
}

export interface Attachment {
  name: string
  type: string
  size: number
  preview?: string
  content?: string
}

export interface DialogToolCall {
  id: string
  name: string
  args: Record<string, unknown>
  content: string
  collapsed: boolean
}

export interface DialogMessage {
  id: number
  role: string
  content: string
  attachments?: Attachment[]
}
