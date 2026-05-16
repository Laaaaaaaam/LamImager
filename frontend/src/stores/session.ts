import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { sessionApi } from '../api/session'
import type { SessionInfo, Message, AgentStreamState, AgentStreamStep, LamEvent } from '../types'

export interface CheckpointInfo {
  visible: boolean
  message: string
  previewUrl?: string
  imageUrls?: string[]
  stepDescription?: string
  toolName?: string
}

const KEY_NODES = ['intent', 'planner', 'executor', 'critic', 'decision']

function stepGroup(name: string): 'key' | 'internal' {
  return KEY_NODES.includes(name) ? 'key' : 'internal'
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<SessionInfo[]>([])
  const currentSessionId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const loading = ref(false)
  const selectedSkillIds = ref<string[]>([])
  const agentStreamStates = reactive(new Map<string, AgentStreamState>())
  const checkpointStates = reactive(new Map<string, CheckpointInfo>())
  let fetchSeq = 0

  function getAgentStream(sessionId: string): AgentStreamState | undefined {
    return agentStreamStates.get(sessionId)
  }

  function clearAgentStream(sessionId: string) {
    agentStreamStates.delete(sessionId)
  }

  function getCheckpoint(sessionId: string): CheckpointInfo | undefined {
    return checkpointStates.get(sessionId)
  }

  function clearCheckpoint(sessionId: string) {
    checkpointStates.delete(sessionId)
  }

  function handleAgentStarted(sessionId: string, event: LamEvent) {
    if (agentStreamStates.has(sessionId)) return
    agentStreamStates.set(sessionId, {
      sessionId,
      status: 'thinking',
      content: '',
      steps: [],
      cost: null,
      startedAt: Date.now(),
    })
  }

  function handleAgentToken(sessionId: string, event: LamEvent) {
    const state = agentStreamStates.get(sessionId)
    if (!state) return
    const node = event.payload.node || ''
    if (node) {
      const nodeStep = state.steps.find(s => s.type === 'node_progress' && s.name === node && s.status === 'running')
      if (nodeStep) {
        nodeStep.content = (nodeStep.content || '') + (event.payload.content || '')
      }
    }
    state.content += event.payload.content || ''
    state.status = 'thinking'
  }

  function handleToolCall(sessionId: string, event: LamEvent) {
    const state = agentStreamStates.get(sessionId)
    if (!state) return
    state.steps.push({
      id: event.event_id,
      type: 'tool_call',
      name: event.payload.name || '',
      status: 'running',
      group: 'key',
      args: event.payload.args,
    })
    state.status = 'tool_running'
  }

  function handleToolResult(sessionId: string, event: LamEvent) {
    const state = agentStreamStates.get(sessionId)
    if (!state) return
    const step = [...state.steps].reverse().find(s => s.name === event.payload.name && s.status === 'running')
    if (step) {
      step.status = 'done'
      step.content = event.payload.content
      step.meta = event.payload.meta
    }
    state.status = 'thinking'
  }

  function handleNodeProgress(sessionId: string, event: LamEvent) {
    const state = agentStreamStates.get(sessionId)
    if (!state) return
    const nodeName = event.payload.node || ''

    if (nodeName === 'decision' && event.payload.detail?.result) {
      const result = event.payload.detail.result as string
      const rollbackMap: Record<string, string> = {
        retry_prompt: 'prompt_builder',
        retry_step: 'executor',
        replan: 'planner',
      }
      const target = rollbackMap[result]
      if (target) {
        const idx = state.steps.findIndex(s => s.name === target)
        if (idx >= 0) state.steps.splice(idx)
      }
    }

    const existingStep = state.steps.find(s => s.type === 'node_progress' && s.name === nodeName)
    if (existingStep) {
      const newStatus = event.payload.status || 'done'
      const stepContent = event.payload.content || event.payload.message || ''
      if (nodeName === 'executor' && newStatus === 'step_done' && event.payload.detail) {
        const completedSteps = (existingStep.meta?.completed_steps as any[]) || []
        completedSteps.push(event.payload.detail)
        existingStep.meta = { ...existingStep.meta, completed_steps: completedSteps }
        existingStep.content = stepContent
      } else {
        existingStep.status = newStatus
        existingStep.content = stepContent
        existingStep.meta = event.payload.detail
      }
    } else {
      const stepContent = event.payload.content || event.payload.message || ''
      if (nodeName === 'executor' && event.payload.status === 'step_done' && event.payload.detail) {
        state.steps.push({
          id: event.event_id,
          type: 'node_progress',
          name: nodeName,
          status: 'running',
          group: stepGroup(nodeName),
          content: stepContent,
          meta: { completed_steps: [event.payload.detail] },
        })
      } else {
        state.steps.push({
          id: event.event_id,
          type: 'node_progress',
          name: nodeName,
          status: event.payload.status || 'done',
          group: stepGroup(nodeName),
          content: stepContent,
          meta: event.payload.detail,
        })
      }
    }
    if (event.payload.status === 'running') {
      state.status = 'thinking'
    }
  }

  function handleToolWarning(sessionId: string, event: LamEvent) {
    const state = agentStreamStates.get(sessionId)
    if (!state) return
    state.steps.push({
      id: event.event_id,
      type: 'tool_call',
      name: event.payload.name || 'warning',
      status: 'error',
      group: 'key',
      content: event.payload.content || event.payload.message || '',
    })
  }

  function handleAgentDone(sessionId: string, event: LamEvent) {
    const state = agentStreamStates.get(sessionId)
    if (!state) return
    state.status = 'done'
    state.cost = event.payload.cost || null
    for (const step of state.steps) {
      if (step.status === 'running' || step.status === 'step_done') step.status = 'done'
    }
    fetchMessages(sessionId)
    fetchSessions()
  }

  function handleAgentError(sessionId: string, event: LamEvent) {
    const state = agentStreamStates.get(sessionId)
    if (!state) return
    state.status = 'error'
    state.content = (state.content || '') + '\n\n[错误] ' + (event.payload.content || event.payload.message || '未知错误')
    fetchMessages(sessionId)
    fetchSessions()
  }

  function handleAgentCancelled(sessionId: string, event: LamEvent) {
    const state = agentStreamStates.get(sessionId)
    if (!state) return
    state.status = 'cancelled'
    state.content += '\n\n[已取消]'
    fetchMessages(sessionId)
    fetchSessions()
  }

  function handleCheckpoint(sessionId: string, event: LamEvent) {
    if (checkpointStates.has(sessionId) && checkpointStates.get(sessionId)?.visible) return
    const artifacts = (event.payload as any).artifacts || []
    const imageUrls = artifacts.filter((a: any) => a.type === 'image').map((a: any) => a.url)
    checkpointStates.set(sessionId, {
      visible: true,
      message: event.payload.message || '确认执行',
      toolName: event.payload.tool_name,
      previewUrl: imageUrls[0] || '',
      imageUrls,
      stepDescription: (event.payload as any).step?.description || '',
    })
  }

  function handleTaskCompleted(sessionId: string) {
    if (sessionId && sessionId !== currentSessionId.value) {
      agentStreamStates.delete(sessionId)
      checkpointStates.delete(sessionId)
    }
  }

  async function fetchSessions() {
    loading.value = true
    try {
      const { data } = await sessionApi.list()
      sessions.value = data
    } catch (e) {
      console.error('Failed to fetch sessions:', e)
    } finally {
      loading.value = false
    }
  }

  async function createSession(title: string = '新会话') {
    try {
      const { data } = await sessionApi.create(title)
      sessions.value.unshift(data)
      currentSessionId.value = data.id
      await fetchMessages(data.id)
      return data
    } catch (e) {
      console.error('Failed to create session:', e)
      throw e
    }
  }

  async function selectSession(id: string) {
    currentSessionId.value = id
    const seq = ++fetchSeq
    try {
      const { data } = await sessionApi.getMessages(id)
      if (seq === fetchSeq) {
        messages.value = data
      }
    } catch (e) {
      if (seq === fetchSeq) {
        console.error('Failed to fetch messages:', e)
      }
    }
  }

  async function fetchMessages(sessionId: string) {
    const seq = ++fetchSeq
    try {
      const { data } = await sessionApi.getMessages(sessionId)
      if (seq === fetchSeq) {
        messages.value = data
      }
    } catch (e) {
      if (seq === fetchSeq) {
        console.error('Failed to fetch messages:', e)
      }
    }
  }

  async function sendMessage(content: string, messageType: string = 'text', metadata: Record<string, unknown> = {}) {
    if (!currentSessionId.value) return
    try {
      await sessionApi.addMessage(currentSessionId.value, { content, message_type: messageType, metadata })
      await fetchMessages(currentSessionId.value)
    } catch (e) {
      console.error('Failed to send message:', e)
      throw e
    }
  }

  async function generate(sessionId: string, data: { prompt: string; negative_prompt?: string; image_count?: number; image_size?: string | undefined; optimize_directions?: string[]; custom_optimize_instruction?: string; reference_images?: string[]; reference_labels?: { index: number; source: string; name: string }[]; context_messages?: { role: string; content: string; image_urls?: string[] }[]; plan_strategy?: string; agent_mode?: boolean; agent_tools?: string[]; agent_plan_strategy?: string }) {
    try {
      const { data: result } = await sessionApi.generate({
        ...data,
        session_id: sessionId,
        skill_ids: selectedSkillIds.value,
      })
      if (data.agent_mode) {
        return result
      }
      if (sessionId === currentSessionId.value) {
        await fetchMessages(sessionId)
      }
      await fetchSessions()
      return result
    } catch (e) {
      console.error('Failed to generate:', e)
      throw e
    }
  }

  async function deleteSession(id: string) {
    try {
      await sessionApi.delete(id)
      sessions.value = sessions.value.filter((s) => s.id !== id)
      if (currentSessionId.value === id) {
        currentSessionId.value = sessions.value.length ? sessions.value[0].id : null
        if (currentSessionId.value) await fetchMessages(currentSessionId.value)
        else messages.value = []
      }
    } catch (e) {
      console.error('Failed to delete session:', e)
      throw e
    }
  }

  async function renameSession(id: string, title: string) {
    try {
      await sessionApi.update(id, { title })
      await fetchSessions()
    } catch (e) {
      console.error('Failed to rename session:', e)
      throw e
    }
  }

  return {
    sessions, currentSessionId, messages, loading, selectedSkillIds,
    agentStreamStates, checkpointStates,
    getAgentStream, clearAgentStream, getCheckpoint, clearCheckpoint,
    handleAgentStarted, handleAgentToken, handleToolCall, handleToolResult,
    handleNodeProgress, handleToolWarning, handleAgentDone, handleAgentError,
    handleAgentCancelled, handleCheckpoint, handleTaskCompleted,
    fetchSessions, createSession, selectSession, fetchMessages,
    sendMessage, generate, deleteSession, renameSession,
  }
})