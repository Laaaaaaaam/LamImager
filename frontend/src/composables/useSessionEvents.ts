import type { TaskUpdateEvent } from '../types'

export function useSessionEvents(
  onTaskUpdate: (event: TaskUpdateEvent) => void,
  onSnapshot: (tasks: Record<string, { status: string; progress: number; total: number; message: string }>) => void,
) {
  let eventSource: EventSource | null = null

  function connect() {
    eventSource = new EventSource('/api/sessions/events')

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === 'task_update') {
          onTaskUpdate(data.data)
        } else if (data.type === 'snapshot') {
          onSnapshot(data.data)
        }
      } catch { /* ignore parse errors */ }
    }

    eventSource.onerror = () => {
      // EventSource 内置自动重连
    }
  }

  function disconnect() {
    eventSource?.close()
    eventSource = null
  }

  return { connect, disconnect }
}
