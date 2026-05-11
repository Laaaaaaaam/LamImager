import type { LamEvent, TaskUpdateEvent } from '../types'

let lastEventId: string | null = null

export function useSessionEvents(
  onTaskUpdate: (event: TaskUpdateEvent) => void,
  onSnapshot: (tasks: Record<string, { status: string; progress: number; total: number; message: string }>) => void,
  onAgentEvent?: (event: LamEvent) => void,
) {
  let abortController: AbortController | null = null
  let retryCount = 0
  const BASE_DELAY = 1000

  function getRetryDelay(): number {
    const delay = Math.min(BASE_DELAY * Math.pow(2, retryCount), 30000)
    retryCount++
    return delay
  }

  function resetRetry() {
    retryCount = 0
  }

  async function connect() {
    abortController = new AbortController()

    try {
      const headers: Record<string, string> = {}
      if (lastEventId) {
        headers['Last-Event-ID'] = lastEventId
      }

      const response = await fetch('/api/sessions/events', {
        headers,
        signal: abortController.signal,
      })

      if (!response.ok || !response.body) {
        setTimeout(connect, getRetryDelay())
        return
      }

      resetRetry()

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('id: ')) {
            lastEventId = line.substring(4).trim()
          } else if (line.startsWith('data: ')) {
            const jsonStr = line.substring(6)
            try {
              const data = JSON.parse(jsonStr)

              if (data.event_type === 'task_progress' && data.payload?.type === 'task_progress') {
                onTaskUpdate({
                  session_id: data.payload.session_id,
                  status: data.payload.status,
                  progress: data.payload.progress,
                  total: data.payload.total,
                  message: data.payload.message,
                  task_type: data.payload.task_type,
                  strategy: data.payload.strategy,
                })
              } else if (data.event_type === 'snapshot') {
                onSnapshot(data.data)
              } else if (
                ['task_started', 'task_progress', 'checkpoint_required', 'task_completed', 'task_failed'].includes(data.event_type) &&
                onAgentEvent
              ) {
                onAgentEvent(data as LamEvent)
              }
            } catch {
              /* ignore parse errors */
            }
          }
        }
      }

      setTimeout(connect, getRetryDelay())
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setTimeout(connect, getRetryDelay())
      }
    }
  }

  function disconnect() {
    abortController?.abort()
    abortController = null
  }

  return { connect, disconnect }
}
