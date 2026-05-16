import api from './client'
import { parseSSEStream } from './sse'
import type { PromptOptimizeResult } from '../types'

export const promptApi = {
  optimize: (prompt: string, direction: string, llmProviderId: string, sessionId?: string, multimodalContext?: Record<string, unknown>[]) =>
    api.post<PromptOptimizeResult>('/prompt/optimize', {
      prompt,
      direction,
      llm_provider_id: llmProviderId,
      session_id: sessionId || null,
      multimodal_context: multimodalContext || null,
    }),

  optimizeStream: async function* (
    prompt: string,
    direction: string,
    llmProviderId: string,
    sessionId: string | null = null,
    signal?: AbortSignal,
  ): AsyncGenerator<string, void, unknown> {
    const response = await fetch('/api/prompt/optimize/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, direction, llm_provider_id: llmProviderId, session_id: sessionId }),
      signal,
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Optimize stream request failed')
    }

    for await (const data of parseSSEStream(response, signal)) {
      if (data.token) yield data.token as string
      if (data.done) return
    }
  },

  streamChat: async function* (
    messages: { role: string; content: string }[],
    providerId: string,
    sessionId: string | null = null,
    temperature: number = 0.7,
    signal?: AbortSignal,
  ): AsyncGenerator<string, void, unknown> {
    const response = await fetch('/api/prompt/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages, provider_id: providerId, session_id: sessionId, temperature, stream_type: 'assistant' }),
      signal,
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Stream request failed')
    }

    for await (const data of parseSSEStream(response, signal)) {
      if (data.token) yield data.token as string
      if (data.done) return
    }
  },

  streamChatWithTools: async function* (
    messages: { role: string; content: string }[],
    providerId: string,
    tools: string[],
    sessionId: string | null = null,
    temperature: number = 0.7,
    signal?: AbortSignal,
  ): AsyncGenerator<{ type: string; data: unknown }, void, unknown> {
    const response = await fetch('/api/prompt/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages, provider_id: providerId, session_id: sessionId, temperature, stream_type: 'assistant', tools }),
      signal,
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Stream request failed')
    }

    for await (const data of parseSSEStream(response, signal)) {
      if (data.token) yield { type: 'token', data: data.token }
      if (data.tool_call) yield { type: 'tool_call', data: data.tool_call }
      if (data.tool_result) yield { type: 'tool_result', data: data.tool_result }
      if (data.done) yield { type: 'done', data }
    }
  },

  planStream: async function* (
    messages: { role: string; content: string }[],
    providerId: string,
    sessionId: string | null = null,
    temperature: number = 0.7,
    signal?: AbortSignal,
  ): AsyncGenerator<string, void, unknown> {
    const response = await fetch('/api/prompt/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages, provider_id: providerId, session_id: sessionId, temperature }),
      signal,
    })

    if (!response.ok) {
      const err = await response.json()
      throw new Error(err.detail || 'Plan stream request failed')
    }

    for await (const data of parseSSEStream(response, signal)) {
      if (data.token) yield data.token as string
      if (data.done) return
    }
  },
}
