import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sessionApi } from '../api/session'
import type { SessionInfo, Message, AgentStreamState } from '../types'

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<SessionInfo[]>([])
  const currentSessionId = ref<string | null>(null)
  const messages = ref<Message[]>([])
  const loading = ref(false)
  const selectedSkillIds = ref<string[]>([])
  const agentStreamStates = ref<Map<string, AgentStreamState>>(new Map())
  let fetchSeq = 0

  function getAgentStream(sessionId: string): AgentStreamState | undefined {
    return agentStreamStates.value.get(sessionId)
  }

  function setAgentStream(sessionId: string, state: AgentStreamState) {
    agentStreamStates.value.set(sessionId, state)
    agentStreamStates.value = new Map(agentStreamStates.value)
  }

  function clearAgentStream(sessionId: string) {
    agentStreamStates.value.delete(sessionId)
    agentStreamStates.value = new Map(agentStreamStates.value)
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
    agentStreamStates, getAgentStream, setAgentStream, clearAgentStream,
    fetchSessions, createSession, selectSession, fetchMessages,
    sendMessage, generate, deleteSession, renameSession,
  }
})