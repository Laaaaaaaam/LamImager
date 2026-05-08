import api from './client'
import type { PromptOptimizeResult } from '../types'

export const promptApi = {
  optimize: (prompt: string, direction: string, llmProviderId: string) =>
    api.post<PromptOptimizeResult>('/prompt/optimize', {
      prompt,
      direction,
      llm_provider_id: llmProviderId,
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

    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        if (signal?.aborted) break
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.error) throw new Error(data.error)
              if (data.token) yield data.token
              if (data.done) return
            } catch (e: any) {
              if (e.message !== 'Unknown' && !e.message.startsWith('data:')) {
                throw e
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
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

    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        if (signal?.aborted) break
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.error) throw new Error(data.error)
              if (data.token) yield data.token
              if (data.done) return
            } catch (e: any) {
              if (e.message !== 'Unknown' && !e.message.startsWith('data:')) {
                throw e
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
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

    const reader = response.body?.getReader()
    if (!reader) throw new Error('No response body')

    const decoder = new TextDecoder()
    let buffer = ''

    try {
      while (true) {
        if (signal?.aborted) break
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.error) throw new Error(data.error)
              if (data.token) yield data.token
              if (data.done) return
            } catch (e: any) {
              if (e.message !== 'Unknown' && !e.message.startsWith('data:')) {
                throw e
              }
            }
          }
        }
      }
    } finally {
      reader.releaseLock()
    }
  },
}
