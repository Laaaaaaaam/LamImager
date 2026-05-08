<template>
  <div class="session-page">
    <div class="session-list" :class="{ collapsed: sessionListCollapsed }">
      <div class="session-list-header">
        <span v-if="!sessionListCollapsed" class="session-list-label">会话</span>
        <button class="session-list-toggle" @click="sessionListCollapsed = !sessionListCollapsed" :title="sessionListCollapsed ? '展开' : '折叠'">
          <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline v-if="sessionListCollapsed" points="9 18 15 12 9 6"/><polyline v-else points="15 18 9 12 15 6"/></svg>
        </button>
      </div>
      <button class="btn btn-primary new-session-btn" @click="newSession" v-if="!sessionListCollapsed">+ 新建会话</button>
      <div class="session-items" v-if="!sessionListCollapsed">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="session-item"
          :class="{ active: s.id === currentSessionId }"
          @click="selectSession(s.id)"
          @contextmenu.prevent="showContextMenu($event, s)"
        >
          <div class="session-title-row">
            <span class="session-title">{{ s.title }}</span>
            <span v-if="getSessionStatus(s.id) === 'generating'" class="status-badge generating">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 生成中
            </span>
            <span v-else-if="getSessionStatus(s.id) === 'optimizing'" class="status-badge optimizing">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 优化中
            </span>
            <span v-else-if="getSessionStatus(s.id) === 'planning'" class="status-badge planning">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> 规划中
            </span>
            <span v-else-if="getSessionStatus(s.id) === 'error'" class="status-badge error">
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> 错误
            </span>
          </div>
          <div class="session-meta">
            <span>{{ s.cost > 0 ? '¥' + s.cost.toFixed(2) : '¥0.00' }}</span>
            <span>{{ formatTokens(s.tokens) }}</span>
            <span v-if="getTaskProgress(s.id)" class="task-progress">{{ getTaskProgress(s.id) }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-area">
      <div class="messages" ref="messagesContainer">
        <div v-if="!currentSessionId" class="empty-state">
          <p>选择或创建一个会话开始</p>
        </div>
        <div v-for="msg in messages" :key="msg.id" class="message" :class="msg.role">
          <div class="message-content" :class="msg.message_type">
            <template v-if="msg.message_type === 'text'">
              <p>{{ msg.content }}</p>
            </template>
            <template v-else-if="msg.message_type === 'image'">
              <p>{{ msg.content }}</p>
              <div class="image-grid">
                <div v-for="(url, i) in (msg.metadata?.image_urls || [])" :key="i" class="image-item">
                  <img :src="url" :alt="'图片 ' + (i + 1)" @click="openImage(url)" @contextmenu.prevent="showImageContextMenu($event, url)" />
                  <label class="image-check">
                    <input type="checkbox" :value="url" v-model="selectedImages" />
                  </label>
                </div>
              </div>
              <div class="image-actions" v-if="(msg.metadata?.image_urls || []).length">
                <button class="btn btn-sm" @click="downloadSelected" :disabled="!selectedImages.length">
                  下载选中({{ selectedImages.length }})
                </button>
                <button class="btn btn-sm" @click="downloadAll(msg.metadata?.image_urls || [])">全部下载</button>
                <button class="btn btn-sm" @click="compareSelected" :disabled="selectedImages.length < 2">
                  对比选中
                </button>
                <button class="btn btn-sm" @click="enterRefineMode(msg)" :disabled="!selectedImages.length">
                  精修({{ selectedImages.length }})
                </button>
              </div>
            </template>
            <template v-else-if="msg.message_type === 'optimization'">
              <p>{{ msg.content }}</p>
              <div class="optimization-compare">
                <div class="compare-side">
                  <div class="compare-label">原始</div>
                  <div class="compare-text">{{ msg.metadata?.original }}</div>
                </div>
                <div class="compare-side">
                  <div class="compare-label">优化后</div>
                  <div class="compare-text optimized">{{ msg.metadata?.optimized }}</div>
                </div>
              </div>
              <button class="btn btn-sm" @click="applyOptimized(msg.metadata?.optimized || '')">应用优化</button>
              <button class="btn btn-sm" @click="applyOptimized(msg.metadata?.original || '')">使用原始</button>
            </template>
            <template v-else-if="msg.message_type === 'plan'">
              <div class="plan-card">
                <div class="plan-card-header" @click="togglePlanCard(msg.id)">
                  <div class="plan-card-title">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                    <span>{{ msg.content }}</span>
                  </div>
                  <div class="plan-card-meta">
                    <span class="plan-step-count">{{ (msg.metadata?.steps || []).length }} 个步骤</span>
                    <svg :class="['plan-chevron', { expanded: expandedPlanIds.has(msg.id) }]" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"/></svg>
                  </div>
                </div>
                <div class="plan-card-body" v-if="expandedPlanIds.has(msg.id) && msg.metadata?.steps">
                  <div v-for="(step: any, i: number) in (msg.metadata.steps as any[])" :key="i" class="plan-card-step">
                    <div class="plan-step-header">
                      <span class="step-num">{{ i + 1 }}</span>
                      <span class="step-prompt-preview">{{ step.description || step.prompt.slice(0, 80) }}{{ (!step.description && step.prompt.length > 80) ? '...' : '' }}</span>
                    </div>
                    <div class="plan-step-detail">
                      <div class="step-field">
                        <label>Prompt</label>
                        <p>{{ step.prompt }}</p>
                      </div>
                      <div class="step-field" v-if="step.negative_prompt">
                        <label>Negative Prompt</label>
                        <p>{{ step.negative_prompt }}</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </template>
            <template v-else-if="msg.message_type === 'error'">
              <p class="error-text">{{ msg.content }}</p>
            </template>
            <template v-else-if="msg.message_type === 'agent'">
              <div class="agent-card">
                <div class="agent-card-header">
                  <span class="agent-badge">Agent</span>
                  <span class="agent-cost" v-if="msg.metadata?.cost">费用 ¥{{ (msg.metadata.cost as number)?.toFixed(4) }}</span>
                </div>
                <div v-if="msg.metadata?.steps && (msg.metadata.steps as any[]).length" class="agent-steps">
                  <div v-for="(step: any, si: number) in msg.metadata.steps" :key="si" class="agent-step">
                    <span class="agent-step-icon">{{ step.type === 'tool_call' ? '>' : step.type === 'tool_result' ? '<' : 'i' }}</span>
                    <span class="agent-step-name">{{ step.name }}</span>
                  </div>
                </div>
                <div class="agent-card-content">{{ msg.content }}</div>
              </div>
            </template>
            <template v-else>
              <p>{{ msg.content }}</p>
            </template>
          </div>
        </div>
        <div v-if="currentSessionId && isSessionBusy(currentSessionId)" class="message assistant">
          <div class="message-content generating">
            <div class="generating-indicator">
              <span class="dot"></span>
              <span class="dot"></span>
              <span class="dot"></span>
            </div>
            <span class="generating-text">{{ generatingText }}</span>
          </div>
        </div>
      </div>

      <div class="compare-overlay" v-if="comparingImages.length" @click.self="comparingImages = []">
        <div class="compare-view">
          <div class="compare-header">
            <span>图片对比（{{ comparingImages.length }}张）</span>
            <button class="btn btn-sm" @click="comparingImages = []">关闭对比</button>
          </div>
          <div class="compare-images">
            <img v-for="(url, i) in comparingImages" :key="i" :src="url" class="compare-img" />
          </div>
          <button class="btn btn-sm" @click="downloadAll(comparingImages)">下载全部</button>
        </div>
      </div>

      <div class="lightbox-overlay" v-if="lightboxUrl" @click.self="lightboxUrl = ''">
        <div class="lightbox-content">
          <button class="lightbox-close" @click="lightboxUrl = ''">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
          <img :src="lightboxUrl" class="lightbox-img" @click.stop />
          <div class="lightbox-actions">
            <button class="btn btn-sm" @click="downloadOne(lightboxUrl)">下载</button>
            <button class="btn btn-sm" @click="openInNewTab(lightboxUrl)">新窗口打开</button>
          </div>
        </div>
      </div>

      <div class="input-area">
        <div class="refine-header" v-if="isRefineMode">
          <span class="refine-label">精修模式</span>
          <button class="btn btn-sm" @click="exitRefineMode">退出精修</button>
        </div>
        <div class="input-main">
          <div class="refine-strip" v-if="contextImageList.length">
            <div v-for="(img, i) in contextImageList" :key="i" class="refine-strip-item">
              <div class="refine-strip-thumb-wrap">
                <img :src="img.preview || img.url" class="refine-strip-thumb" />
                <span class="refine-strip-badge">{{ i + 1 }}</span>
              </div>
              <span class="refine-strip-label">{{ img.source === 'upload' ? img.name : (img.source === 'refine' ? '精修' : '上下文') }}</span>
              <button class="attachment-remove" @click="removeContextImage(i)">x</button>
            </div>
            <label class="refine-add-btn" title="追加图片">
              <input type="file" accept="image/*" multiple @change="handleFileUpload($event, 'image')" hidden />
              + 追加
            </label>
          </div>
          <textarea
            ref="mainTextarea"
            v-model="inputText"
            :placeholder="isRefineMode ? '基于参考图进行修改...' : '输入生图指令...'"
            rows="2"
            @input="autoResizeTextarea"
            @keydown.enter.exact.prevent="sendGenerate"
          ></textarea>
          <input
            v-if="!agentMode"
            v-model="negativePrompt"
            type="text"
            class="negative-input"
            placeholder="反向提示词（可选）"
          />
        </div>
          <div class="input-controls">
          <div v-if="!agentMode" class="input-options">
            <label class="upload-btn" title="上传图片">
              <input type="file" accept="image/*" multiple @change="handleFileUpload($event, 'image')" hidden />
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
            </label>
            <label class="upload-btn" title="上传文档">
              <input type="file" accept=".txt,.md,.pdf,.doc,.docx" multiple @change="handleFileUpload($event, 'doc')" hidden />
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            </label>
            <span class="option-label">数量:</span>
            <button
              v-for="n in [1, 2, 4, 8]" :key="n"
              class="count-btn"
              :class="{ active: imageCount === n }"
              @click="imageCount = n"
            >{{ n }}</button>
            <span class="option-label size-label">尺寸:</span>
            <input
              v-model.number="imageWidth"
              type="number"
              class="size-input"
              :min="noSizeLimit ? undefined : 64"
              step="1"
            />
            <span class="size-sep">×</span>
            <input
              v-model.number="imageHeight"
              type="number"
              class="size-input"
              :min="noSizeLimit ? undefined : 64"
              step="1"
            />
            <label class="no-limit-label">
              <input type="checkbox" v-model="noSizeLimit" />
              无限制
            </label>
          </div>
          <div class="input-actions">
            <button class="btn btn-sm" @click="agentMode = !agentMode" :class="{ 'btn-primary': agentMode }" :title="agentMode ? 'Agent 模式' : '正常模式'">
              智能
            </button>
            <button class="btn btn-sm" @click="showAssistant = !showAssistant" :class="{ 'btn-primary': showAssistant }">
              助手
            </button>
            <button class="btn btn-primary btn-sm" @click="sendGenerate" :disabled="!inputText.trim() || (currentSessionId && isSessionBusy(currentSessionId))">
              {{ (currentSessionId && isSessionBusy(currentSessionId)) ? '任务进行中...' : (isRefineMode ? '精修发送' : (agentMode ? 'Agent发送' : '发送')) }}
            </button>
            <button
              v-if="agentMode && currentSessionId && isSessionBusy(currentSessionId)"
              class="btn btn-sm btn-danger"
              @click="cancelAgent"
            >取消</button>
          </div>
        </div>
      </div>
    </div>

    <div class="assistant-sidebar" v-if="showAssistant" :class="{ expanded: assistantExpanded }">
      <div class="assistant-header">
        <div class="assistant-tabs">
          <button
            v-for="tab in assistantTabs" :key="tab.key"
            class="tab-btn"
            :class="{ active: assistantTab === tab.key }"
            @click="assistantTab = tab.key"
          >{{ tab.label }}</button>
        </div>
        <div class="assistant-header-actions">
          <button class="btn btn-sm assistant-toggle-btn" @click="assistantExpanded = !assistantExpanded" :title="assistantExpanded ? '收缩' : '展开'">
            <svg v-if="assistantExpanded" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <button class="btn btn-sm" @click="showAssistant = false">关闭</button>
        </div>
      </div>

      <div class="assistant-content">
        <div v-if="assistantTab === 'dialog'" class="tab-dialog">
          <div class="dialog-config-bar">
            <div class="context-toggle" style="border: none; margin-bottom: 0;">
              <button
                class="toggle-btn"
                :class="{ active: responseStyle === 'default' }"
                @click="responseStyle = 'default'"
              >默认</button>
              <button
                class="toggle-btn"
                :class="{ active: responseStyle === 'verbose' }"
                @click="responseStyle = 'verbose'"
              >详细</button>
              <button
                class="toggle-btn"
                :class="{ active: responseStyle === 'concise' }"
                @click="responseStyle = 'concise'"
              >简洁</button>
            </div>
            <button class="dialog-settings-btn" :class="{ active: showDialogSettings }" @click="showDialogSettings = !showDialogSettings" title="更多设置">
              <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            </button>
          </div>
          <div v-if="showDialogSettings" class="dialog-settings-panel">
            <div class="context-toggle">
              <button class="toggle-btn" :class="{ active: contextMode === 'shared' }" @click="contextMode = 'shared'">共享上下文</button>
              <button class="toggle-btn" :class="{ active: contextMode === 'current' }" @click="contextMode = 'current'">仅当前输入</button>
            </div>
            <div class="context-toggle" style="margin-top: 6px;">
              <button class="toggle-btn" :class="{ active: memoryMode === 'global' }" @click="memoryMode = 'global'">全局跨窗口</button>
              <button class="toggle-btn" :class="{ active: memoryMode === 'session' }" @click="memoryMode = 'session'">仅当前会话</button>
            </div>
          </div>
          <div class="dialog-messages" ref="dialogContainer">
            <div v-for="m in dialogMessages" :key="m.id" class="dialog-msg" :class="m.role">
              <template v-if="m.attachments && m.attachments.length">
                <div class="msg-attachments">
                  <img v-for="(att, i) in m.attachments" :key="i" v-if="att.type.startsWith('image/')" :src="att.preview" class="msg-attachment-thumb" />
                </div>
              </template>
              <div class="dialog-msg-content">{{ m.content }}</div>
              <button class="dialog-msg-copy" @click="copyToClipboard(m.content)" title="复制">
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
              </button>
            </div>
          </div>
          <div v-if="dialogToolCalls.length" class="tool-calls-area">
            <div v-for="tc in dialogToolCalls" :key="tc.id" class="tool-call-card" :class="{ collapsed: tc.collapsed }">
              <div class="tool-call-header" @click="tc.collapsed = !tc.collapsed">
                <span class="tool-call-badge">{{ tc.name === 'web_search' ? '搜索' : tc.name === 'image_search' ? '图片搜索' : tc.name }}</span>
                <span class="tool-call-status">{{ tc.content ? '完成' : '执行中...' }}</span>
              </div>
              <div v-if="!tc.collapsed" class="tool-call-body">
                <div v-if="tc.content" class="tool-call-content">{{ tc.content }}</div>
                <div v-else class="tool-call-loading">搜索中...</div>
              </div>
            </div>
          </div>
          <div class="dialog-actions">
            <button class="btn btn-sm" @click="saveDialogHistory" :disabled="!dialogMessages.length">保存对话</button>
            <button class="btn btn-sm" @click="clearDialog" :disabled="!dialogMessages.length">清除对话</button>
          </div>
          <div class="dialog-input-area">
            <div class="dialog-attachment-preview" v-if="dialogAttachments.length">
              <div v-for="(file, i) in dialogAttachments" :key="i" class="dialog-attachment-item">
                <img v-if="file.type.startsWith('image/')" :src="file.preview" class="dialog-attachment-thumb" />
                <span v-else class="dialog-attachment-doc">{{ file.name }}</span>
                <button class="dialog-attachment-remove" @click="dialogAttachments.splice(i, 1)">x</button>
              </div>
            </div>
            <div class="dialog-input-row">
              <label class="dialog-upload-btn" title="上传文件">
                <input type="file" accept="image/*,.txt,.md" multiple @change="handleDialogFileUpload" hidden />
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>
              </label>
              <button class="search-toggle-btn" :class="{ active: searchEnabled }" @click="searchEnabled = !searchEnabled" title="网络搜索">
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
              </button>
              <textarea
                ref="dialogTextarea"
                v-model="dialogInput"
                placeholder="输入消息..."
                class="dialog-textarea"
                rows="1"
                @input="autoResizeDialogTextarea"
                @keydown.enter.exact.prevent="sendDialog"
              />
              <button class="btn btn-sm btn-primary" @click="sendDialog" :disabled="!dialogInput.trim() && !dialogAttachments.length">发送</button>
            </div>
          </div>
        </div>

        <div v-if="assistantTab === 'optimize'" class="tab-optimize">
          <div class="optimize-directions">
            <p class="section-title">优化方向（可多选）</p>
            <label v-for="dir in optimizeDirections" :key="dir.key" class="direction-item">
              <input type="checkbox" :value="dir.key" v-model="selectedDirections" />
              <div class="direction-info">
                <span class="direction-name">{{ dir.label }}</span>
                <span class="direction-desc">{{ dir.desc }}</span>
              </div>
            </label>
            <label class="direction-item">
              <input type="checkbox" value="custom" v-model="selectedDirections" />
              <div class="direction-info">
                <span class="direction-name">自定义</span>
                <span class="direction-desc">输入自定义优化指令</span>
              </div>
            </label>
            <textarea
              v-if="selectedDirections.includes('custom')"
              v-model="customInstruction"
              placeholder="输入自定义优化指令..."
              rows="2"
              class="custom-input"
            ></textarea>
          </div>
          <div class="optimize-preview">
            <p class="section-title">当前提示词</p>
            <div class="preview-text">{{ inputText || '（输入框为空）' }}</div>
          </div>
          <button class="btn btn-primary" style="width: 100%" @click="doOptimize" :disabled="!selectedDirections.length || !inputText.trim() || optimizing">
            {{ optimizing ? '优化中...' : '优化' }}
          </button>
          <div v-if="optimizeResult" class="optimize-result">
            <p class="section-title">优化结果</p>
            <div class="result-text" :class="{ streaming: optimizing }">{{ optimizeResult }}</div>
            <button v-if="!optimizing" class="btn btn-sm" @click="applyOptimizeResult" style="margin-top: 8px">应用优化</button>
          </div>
        </div>

        <div v-if="assistantTab === 'plan'" class="tab-plan">
          <div class="plan-template-section">
            <select v-model="selectedTemplateId" class="template-select" @change="loadTemplate">
              <option value="">从零开始规划</option>
              <option v-for="t in planTemplates" :value="t.id">{{ t.name }}</option>
            </select>
          </div>
          <div v-if="templateVariables.length" class="template-variables">
            <div v-for="v in templateVariables" :key="v.key" class="form-group">
              <label>{{ v.label }}{{ v.required ? ' *' : '' }}</label>
              <input v-model="templateVariableValues[v.key]" :placeholder="v.default" type="text" />
            </div>
            <button class="btn btn-sm" @click="applyTemplateVariables">应用变量</button>
          </div>
          <div class="plan-strategy">
            <p class="section-title">执行策略</p>
            <div class="strategy-options">
              <label v-for="s in planStrategies" :key="s.key" class="strategy-label">
                <input type="radio" :value="s.key" v-model="selectedPlanStrategy" />
                <span>{{ s.label }}</span>
                <span class="strategy-desc">{{ s.desc }}</span>
              </label>
            </div>
          </div>
          <button class="btn btn-primary" style="width: 100%; margin-bottom: 12px" @click="doPlan" :disabled="!inputText.trim() || planning">
            {{ planning ? '规划中...' : '生成规划' }}
          </button>
          <div v-if="planning && planStreamText" class="plan-streaming">
            <p class="section-title">正在规划...</p>
            <div class="stream-text">{{ planStreamText }}</div>
          </div>
          <div v-if="planSteps.length" class="plan-steps">
            <div v-for="(step, i) in planSteps" :key="i" class="plan-step">
              <div class="step-header">
                <span>步骤 {{ i + 1 }}</span>
                <div class="step-actions">
                  <button class="btn-icon" title="上移" @click="moveStep(i, -1)" :disabled="i === 0">↑</button>
                  <button class="btn-icon" title="下移" @click="moveStep(i, 1)" :disabled="i === planSteps.length - 1">↓</button>
                  <button class="btn-icon" title="复制" @click="duplicateStep(i)">⧉</button>
                  <button class="btn-icon" title="删除" @click="planSteps.splice(i, 1)">×</button>
                </div>
              </div>
              <div class="form-group">
                <label>提示词</label>
                <textarea v-model="step.prompt" rows="2"></textarea>
              </div>
              <div class="form-group">
                <label>反向提示词</label>
                <input v-model="step.negative_prompt" type="text" />
              </div>
              <div class="form-group form-row">
                <label>数量 <input type="number" v-model.number="step.image_count" min="1" max="8" style="width:50px" /></label>
                <label>尺寸 <input v-model="step.image_size" type="text" :placeholder="noSizeLimit ? '不限' : `${imageWidth}x${imageHeight}`" style="width:100px" /></label>
              </div>
              <div class="form-group" v-if="step.description">
                <label>说明</label>
                <p class="step-desc">{{ step.description }}</p>
              </div>
            </div>
            <button class="btn btn-sm" @click="planSteps.push({ prompt: '', negative_prompt: '', description: '', image_count: 1 })">+ 添加步骤</button>
            <div class="plan-summary">
              预计生成: {{ planSteps.reduce((sum, s) => sum + (s.image_count || 1), 0) }} 张图片
            </div>
            <button class="btn btn-primary" style="width: 100%" @click="executePlan">确认并执行</button>
            <button class="btn btn-sm" style="width: 100%; margin-top: 6px" @click="saveAsTemplate">保存为模板</button>
          </div>
        </div>

        <div v-if="assistantTab === 'skill'" class="tab-skills">
          <p class="section-title">选择技能（可多选）</p>
          <div v-if="skills.length">
            <div v-for="skill in skills" :key="skill.id" class="skill-item">
              <label class="skill-label">
                <input type="checkbox" :value="skill.id" v-model="selectedSkillIds" />
                <div class="skill-info">
                  <span class="skill-name">{{ skill.name }}</span>
                  <span class="skill-desc">{{ skill.description }}</span>
                </div>
              </label>
            </div>
          </div>
          <div v-else class="empty-hint">暂无技能，请在技能管理中创建</div>
          <p class="hint-text">已选技能将应用于下次生图指令</p>
        </div>
      </div>
    </div>

    <div v-if="planCheckpoint" class="checkpoint-overlay">
      <div class="checkpoint-card">
        <p>{{ planCheckpoint.message }}</p>
        <div class="checkpoint-actions">
          <button class="btn btn-primary" @click="continuePlan">继续执行</button>
          <button class="btn" @click="abortPlan">终止规划</button>
        </div>
      </div>
    </div>

    <div v-if="contextMenu.show" class="context-menu" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }">
      <button @click="renameSession(contextMenu.sessionId!)">重命名</button>
      <button @click="deleteSession(contextMenu.sessionId!)">删除</button>
    </div>
    <div v-if="imageContextMenu.show" class="context-menu" :style="{ left: imageContextMenu.x + 'px', top: imageContextMenu.y + 'px' }">
      <button v-if="!isContextPinned(imageContextMenu.url)" @click="toggleContextPin(imageContextMenu.url)">加入上下文</button>
      <button v-else @click="toggleContextPin(imageContextMenu.url)">从上下文移除</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { useSessionStore } from '../stores/session'
import { useProviderStore } from '../stores/provider'
import { skillApi } from '../api/skill'
import { promptApi } from '../api/prompt'
import { settingsApi } from '../api/settings'
import { sessionApi } from '../api/session'
import { useBillingStore } from '../stores/billing'
import type { Skill, DefaultModelsConfig, TaskHandle, TaskUpdateEvent, PlanStep, PlanTemplate, TemplateVariable } from '../types'
import { dialog } from '../composables/useDialog'
import { useSessionEvents } from '../composables/useSessionEvents'
import { planTemplateApi } from '../api/planTemplate'

const store = useSessionStore()
const providerStore = useProviderStore()
const billingStore = useBillingStore()
const sessions = computed(() => store.sessions)
const currentSessionId = computed(() => store.currentSessionId)
const messages = computed(() => store.messages)

const inputText = ref('')
const agentMode = ref(false)
const negativePrompt = ref('')
const imageCount = ref(1)
const imageWidth = ref(1024)
const imageHeight = ref(1024)
const noSizeLimit = ref(false)
const showAssistant = ref(false)
const assistantTab = ref('dialog')
const selectedImages = ref<string[]>([])
const comparingImages = ref<string[]>([])
const isRefineMode = ref(false)

interface ContextImage {
  url: string
  source: 'upload' | 'context' | 'refine'
  name: string
  preview?: string
}

const contextImageList = ref<ContextImage[]>([])
const contextImageUrls = computed(() => new Set(contextImageList.value.map(x => x.url)))

function addContextImage(url: string, source: ContextImage['source'], name: string, preview?: string) {
  if (contextImageUrls.value.has(url)) return
  contextImageList.value.push({ url, source, name, preview })
}

function removeContextImage(index: number) {
  const img = contextImageList.value[index]
  if (!img) return
  if (img.source === 'upload') {
    const idx = attachments.value.findIndex(a => a.preview === img.url)
    if (idx >= 0) attachments.value.splice(idx, 1)
  }
  contextImageList.value.splice(index, 1)
}

function clearContextImages() {
  contextImageList.value = []
}

function refreshAutoContext() {
  if (isRefineMode.value) return
  const recentUrls: string[] = []
  for (const m of messages.value) {
    if (m.message_type === 'image' && m.metadata?.image_urls) {
      for (const url of (m.metadata.image_urls as string[])) {
        if (!contextImageUrls.value.has(url)) {
          recentUrls.push(url)
        }
      }
    }
  }
  for (const url of recentUrls.slice(-4)) {
    contextImageList.value.push({ url, source: 'context', name: '已生成' })
  }
}

const activeTasks = ref<Map<string, TaskHandle>>(new Map())
const generatingText = ref('生成中...')
const optimizing = ref(false)
const planning = ref(false)
const mainTextarea = ref<HTMLTextAreaElement | null>(null)
const sessionListCollapsed = ref(false)
const assistantExpanded = ref(false)

interface Attachment {
  name: string
  type: string
  size: number
  preview?: string
  content?: string
}

const attachments = ref<Attachment[]>([])
const dialogAttachments = ref<Attachment[]>([])

const assistantTabs = [
  { key: 'dialog', label: '对话' },
  { key: 'optimize', label: '优化' },
  { key: 'plan', label: '规划' },
  { key: 'skill', label: '技能' },
]

const contextMode = ref<'shared' | 'current'>('shared')
const memoryMode = ref<'global' | 'session'>('global')
const dialogMessages = ref<{ id: number; role: string; content: string; attachments?: Attachment[] }[]>([])

const savedMemoryMode = localStorage.getItem('assistantMemoryMode')
if (savedMemoryMode === 'global' || savedMemoryMode === 'session') {
  memoryMode.value = savedMemoryMode
}

const savedDialog = localStorage.getItem('assistantDialogHistory')
if (savedDialog) {
  try {
    dialogMessages.value = JSON.parse(savedDialog)
  } catch { /* ignore */ }
}
const dialogInput = ref('')
const dialogTextarea = ref<HTMLTextAreaElement | null>(null)
const dialogContainer = ref<HTMLElement | null>(null)
const responseStyle = ref<'default' | 'verbose' | 'concise'>('default')
const showDialogSettings = ref(false)

const optimizeDirections = [
  { key: 'detail_enhancement', label: '细节增强', desc: '提升画面细节与清晰度' },
  { key: 'style_unification', label: '风格统一', desc: '统一画面整体风格' },
  { key: 'composition_optimization', label: '构图优化', desc: '优化画面构图与布局' },
  { key: 'color_adjustment', label: '色彩调整', desc: '优化色彩搭配与氛围' },
  { key: 'lighting_enhancement', label: '光影增强', desc: '增强光影效果与层次' },
]
const selectedDirections = ref<string[]>([])
const customInstruction = ref('')
const optimizeResult = ref('')

const planStrategies = [
  { key: 'parallel', label: '并发生成', desc: '所有步骤同时执行，互不依赖' },
  { key: 'sequential', label: '顺序执行', desc: '按步骤逐一执行，每步依赖前一步结果' },
  { key: 'iterative', label: '迭代优化', desc: '每步基于前一步结果优化，逐步精炼' },
]
const selectedPlanStrategy = ref('parallel')

const planTemplates = ref<PlanTemplate[]>([])
const selectedTemplateId = ref('')
const templateVariables = ref<TemplateVariable[]>([])
const templateVariableValues = ref<Record<string, string>>({})

async function loadTemplate() {
  if (!selectedTemplateId.value) {
    templateVariables.value = []
    templateVariableValues.value = {}
    return
  }
  const template = planTemplates.value.find(t => t.id === selectedTemplateId.value)
  if (!template) return
  templateVariables.value = template.variables || []
  templateVariableValues.value = {}
  for (const v of template.variables || []) {
    templateVariableValues.value[v.key] = v.default || ''
  }
  selectedPlanStrategy.value = template.strategy
}

async function applyTemplateVariables() {
  if (!selectedTemplateId.value) return
  try {
    const { data } = await planTemplateApi.apply(selectedTemplateId.value, templateVariableValues.value)
    planSteps.value = (data.steps || []).map((s: any) => ({
      prompt: s.prompt || '',
      negative_prompt: s.negative_prompt || '',
      description: s.description || '',
      image_count: s.image_count || 1,
      image_size: s.image_size || '',
    }))
    templateVariables.value = []
    templateVariableValues.value = {}
    selectedTemplateId.value = ''
  } catch (e: any) {
    dialog.showAlert('应用模板失败: ' + (e.message || '未知错误'))
  }
}

const planSteps = ref<PlanStep[]>([])
const planStreamText = ref('')
const skills = ref<Skill[]>([])
const selectedSkillIds = ref<string[]>([])

const defaultModels = ref<DefaultModelsConfig>({
  default_optimize_provider_id: null,
  default_image_provider_id: null,
  default_plan_provider_id: null,
  default_image_width: 1024,
  default_image_height: 1024,
  max_concurrent: 5,
})

const contextMenu = ref({ show: false, x: 0, y: 0, sessionId: null as string | null })
const imageContextMenu = ref({ show: false, x: 0, y: 0, url: '' })
const messagesContainer = ref<HTMLElement | null>(null)
let contextMenuTimer: ReturnType<typeof setTimeout> | null = null

function isSessionBusy(sessionId: string): boolean {
  const task = activeTasks.value.get(sessionId)
  return task?.status === 'running'
}

function getSessionStatus(sessionId: string): string {
  const task = activeTasks.value.get(sessionId)
  if (task?.status === 'running') return task.type
  if (task?.status === 'error') return 'error'
  return 'idle'
}

function getTaskProgress(sessionId: string): string {
  const task = activeTasks.value.get(sessionId)
  if (!task || task.status !== 'running' || !task.total) return ''
  return `${task.progress}/${task.total}`
}

const { connect: connectEvents, disconnect: disconnectEvents } = useSessionEvents(
  (event: TaskUpdateEvent) => {
    const task = activeTasks.value.get(event.session_id)
    if (task) {
      task.progress = event.progress
      task.total = event.total
      if (event.status === 'idle' || event.status === 'error') {
        task.status = event.status === 'error' ? 'error' : 'done'
        setTimeout(() => activeTasks.value.delete(event.session_id), 3000)
      }
    }
    store.fetchSessions()
  },
  (tasks) => {
    for (const [sid, info] of Object.entries(tasks)) {
      if (info.status !== 'idle') {
        activeTasks.value.set(sid, {
          sessionId: sid,
          type: info.status as TaskHandle['type'],
          status: 'running',
          progress: info.progress,
          total: info.total,
          abortController: null,
        })
      }
    }
  },
)

onMounted(async () => {
  connectEvents()
  await store.fetchSessions()
  if (sessions.value.length) {
    await store.selectSession(sessions.value[0].id)
  } else {
    await store.createSession()
  }
  try {
    const { data } = await skillApi.list()
    skills.value = data
  } catch { /* ignore */ }
  try {
    const { data } = await settingsApi.getDefaultModels()
    defaultModels.value = data
    if (data.default_image_width) imageWidth.value = data.default_image_width
    if (data.default_image_height) imageHeight.value = data.default_image_height
  } catch { /* ignore */ }
  await providerStore.fetchProviders()
    try {
      const { data } = await planTemplateApi.list()
      planTemplates.value = data
    } catch { /* ignore */ }
  })

let streamAbortController: AbortController | null = null

onUnmounted(() => {
  disconnectEvents()
  if (streamAbortController) {
    streamAbortController.abort()
    streamAbortController = null
  }
  if (contextMenuTimer) clearTimeout(contextMenuTimer)
})

watch(messages, () => {
  refreshAutoContext()
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
})

watch(dialogMessages, (val) => {
  if (memoryMode.value === 'global') {
    localStorage.setItem('assistantDialogHistory', JSON.stringify(val))
  }
  nextTick(() => {
    if (dialogContainer.value) {
      dialogContainer.value.scrollTop = dialogContainer.value.scrollHeight
    }
  })
}, { deep: true })

watch(memoryMode, (val) => {
  localStorage.setItem('assistantMemoryMode', val)
  if (val === 'session') {
    localStorage.removeItem('assistantDialogHistory')
  } else {
    localStorage.setItem('assistantDialogHistory', JSON.stringify(dialogMessages.value))
  }
})


function formatTokens(tokens: number) {
  if (tokens >= 1000) return (tokens / 1000).toFixed(1) + 'k tok'
  return tokens + ' tok'
}

async function handleFileUpload(event: Event, type: 'image' | 'doc') {
  const input = event.target as HTMLInputElement
  if (!input.files) return
  
  for (const file of input.files) {
    const attachment: Attachment = {
      name: file.name,
      type: file.type,
      size: file.size,
    }
    
    if (file.type.startsWith('image/')) {
      attachment.preview = await readFileAsDataURL(file)
      addContextImage(attachment.preview, 'upload', file.name, attachment.preview)
    } else {
      attachment.content = await readFileAsText(file)
    }
    
    attachments.value.push(attachment)
  }
  
  input.value = ''
}

async function handleDialogFileUpload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files) return
  
  for (const file of input.files) {
    const attachment: Attachment = {
      name: file.name,
      type: file.type,
      size: file.size,
    }
    
    if (file.type.startsWith('image/')) {
      attachment.preview = await readFileAsDataURL(file)
    } else {
      attachment.content = await readFileAsText(file)
    }
    
    dialogAttachments.value.push(attachment)
  }
  
  input.value = ''
}

function readFileAsDataURL(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsText(file)
  })
}

function autoResizeTextarea() {
  const textarea = mainTextarea.value
  if (!textarea) return
  textarea.style.height = 'auto'
  const newHeight = Math.min(textarea.scrollHeight, 200)
  textarea.style.height = newHeight + 'px'
}

function autoResizeDialogTextarea() {
  const textarea = dialogTextarea.value
  if (!textarea) return
  textarea.style.height = 'auto'
  const newHeight = Math.min(textarea.scrollHeight, 120)
  textarea.style.height = newHeight + 'px'
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text).catch(() => {
    const textarea = document.createElement('textarea')
    textarea.value = text
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
  })
}

function saveDialogHistory() {
  if (!dialogMessages.value.length) return
  const history = dialogMessages.value.map(m => {
    const role = m.role === 'user' ? '用户' : '助手'
    return `[${role}]\n${m.content}`
  }).join('\n\n---\n\n')
  const blob = new Blob([history], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `对话记录_${new Date().toISOString().slice(0, 10)}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

async function clearDialog() {
  if (await dialog.showConfirm('确定要清除当前对话吗？建议先保存对话记录。')) {
    dialogMessages.value.length = 0
    dialogToolCalls.value.length = 0
    localStorage.removeItem('assistantDialogHistory')
  }
}

async function newSession() {
  inputText.value = ''
  negativePrompt.value = ''
  attachments.value = []
  clearContextImages()
  imageCount.value = 1
  imageWidth.value = 1024
  imageHeight.value = 1024
  noSizeLimit.value = false
  selectedDirections.value = []
  customInstruction.value = ''
  optimizeResult.value = ''
  await store.createSession()
}

async function selectSession(id: string) {
  await store.selectSession(id)
  selectedImages.value = []
  clearContextImages()
  inputText.value = ''
  negativePrompt.value = ''
  attachments.value = []
  imageCount.value = 1
  imageWidth.value = 1024
  imageHeight.value = 1024
  noSizeLimit.value = false
  selectedDirections.value = []
  customInstruction.value = ''
  optimizeResult.value = ''
  if (memoryMode.value === 'session') {
    dialogMessages.value.length = 0
  }
  refreshAutoContext()
}

async function cancelAgent() {
  const sid = currentSessionId.value
  if (!sid) return
  try {
    await sessionApi.cancel(sid)
    generatingText.value = '已取消'
  } catch (e: any) {
    console.error('Cancel failed:', e)
  }
}

async function sendGenerate() {
  if (!inputText.value.trim() && !contextImageList.value.length) return
  const sid = currentSessionId.value
  if (!sid || isSessionBusy(sid)) return

  const abortController = new AbortController()
  activeTasks.value.set(sid, {
    sessionId: sid,
    type: 'generate',
    status: 'running',
    progress: 0,
    total: imageCount.value,
    abortController,
  })
  generatingText.value = '生成中...'

  let promptWithContext = inputText.value
  const referenceImages: string[] = []

  const uploadImages = contextImageList.value.filter(x => x.source === 'upload')
  if (uploadImages.length) {
    const labelLines = uploadImages.map((img, i) => `[图${i + 1}: ${img.name}]`).join('\n')
    promptWithContext = labelLines + '\n' + promptWithContext
    for (const img of uploadImages) {
      if (img.preview) referenceImages.push(img.preview)
      else if (img.url.startsWith('data:')) referenceImages.push(img.url)
    }
  }

  const refineImages = contextImageList.value.filter(x => x.source === 'refine')
  if (refineImages.length) {
    const labelLines = refineImages.map((img, i) => `[图${uploadImages.length + i + 1}: ${img.name}]`).join('\n')
    promptWithContext = labelLines + '\n' + promptWithContext
    for (const img of refineImages) {
      const base64 = await fetchImageAsBase64(img.url)
      if (base64) referenceImages.push(base64)
    }
  }

  const docs = attachments.value.filter(a => !a.type.startsWith('image/') && a.content)
  if (docs.length) {
    const docContexts = docs.map(a => `\n[文档内容: ${a.name}]\n${a.content}`).join('\n')
    promptWithContext = promptWithContext + '\n' + docContexts
  }

  const ctxUrls = contextImageList.value
    .filter(img => img.source === 'context')
    .map(img => img.url)

  const contextMessages = messages.value.slice(-10).map(m => {
    const entry: { role: string; content: string; image_urls?: string[] } = {
      role: m.role,
      content: m.content,
    }
    if (m.message_type === 'image' && m.metadata?.image_urls && ctxUrls.length) {
      const urls = (m.metadata.image_urls as string[]).filter((url: string) =>
        ctxUrls.includes(url)
      )
      if (urls.length) {
        entry.image_urls = urls
      }
    }
    return entry
  })

  const refLabels = contextImageList.value
    .filter(img => img.source !== 'context')
    .map((img, i) => ({
      index: i + 1,
      source: img.source,
      name: img.name,
    }))

  try {
    const generateData: any = {
      prompt: promptWithContext,
      negative_prompt: negativePrompt.value,
      image_count: imageCount.value,
      image_size: noSizeLimit.value ? undefined : `${imageWidth.value}x${imageHeight.value}`,
      optimize_directions: selectedDirections.value.filter(d => d !== 'custom'),
      custom_optimize_instruction: customInstruction.value,
      reference_images: referenceImages.length ? referenceImages : undefined,
      reference_labels: refLabels.length ? refLabels : undefined,
      context_messages: contextMessages,
      plan_strategy: '',
    }

    if (agentMode.value) {
      generateData.agent_mode = true
      generateData.agent_tools = ['web_search', 'image_search']
      generateData.agent_plan_strategy = selectedPlanStrategy.value || 'parallel'
    }

    await store.generate(sid, generateData)
    inputText.value = ''
    negativePrompt.value = ''
    selectedImages.value = []
    attachments.value = []
    clearContextImages()
    if (isRefineMode.value) {
      exitRefineMode()
    }
    refreshAutoContext()
  } catch (e: any) {
    dialog.showAlert('发送失败: ' + (e.message || '未知错误'))
    console.error('sendGenerate error:', e)
  } finally {
    const task = activeTasks.value.get(sid)
    if (task) task.status = 'done'
    setTimeout(() => activeTasks.value.delete(sid), 3000)
    billingStore.fetchSummary()
  }
}

const lightboxUrl = ref('')
const expandedPlanIds = ref<Set<string>>(new Set())

function togglePlanCard(msgId: string) {
  if (expandedPlanIds.value.has(msgId)) {
    expandedPlanIds.value.delete(msgId)
  } else {
    expandedPlanIds.value.add(msgId)
  }
  expandedPlanIds.value = new Set(expandedPlanIds.value)
}

function openImage(url: string) {
  lightboxUrl.value = url
}

function downloadOne(url: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = 'image.png'
  a.target = '_blank'
  a.click()
}

function openInNewTab(url: string) {
  window.open(url, '_blank')
}

function downloadAll(urls: string[]) {
  urls.forEach((url) => {
    const a = document.createElement('a')
    a.href = url
    a.download = 'image.png'
    a.target = '_blank'
    a.click()
  })
}

function downloadSelected() {
  downloadAll(selectedImages.value)
}

function compareSelected() {
  comparingImages.value = [...selectedImages.value]
}

function enterRefineMode(_msg?: any) {
  isRefineMode.value = true
  clearContextImages()
  selectedImages.value.forEach((url, i) => {
    addContextImage(url, 'refine', `图${i + 1}`)
  })
  selectedImages.value = []
  inputText.value = ''
}

function exitRefineMode() {
  isRefineMode.value = false
  clearContextImages()
  refreshAutoContext()
}

async function fetchImageAsBase64(url: string): Promise<string> {
  if (url.startsWith('data:')) return url
  try {
    const resp = await fetch(url)
    if (resp.ok) {
      const blob = await resp.blob()
      return await new Promise<string>((resolve) => {
        const reader = new FileReader()
        reader.onloadend = () => resolve(reader.result as string)
        reader.readAsDataURL(blob)
      })
    }
  } catch {}
  const proxyUrl = `/api/images/proxy?url=${encodeURIComponent(url)}`
  const resp = await fetch(proxyUrl)
  if (!resp.ok) return ''
  const blob = await resp.blob()
  return await new Promise<string>((resolve) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result as string)
    reader.readAsDataURL(blob)
  })
}

function applyOptimized(text: string) {
  inputText.value = text
}

let dialogMsgId = 0

async function sendDialog() {
  if (!dialogInput.value.trim() && !dialogAttachments.value.length) return
  const userMsg = dialogInput.value
  const currentAttachments = [...dialogAttachments.value]
  dialogInput.value = ''
  dialogAttachments.value = []

  const llmProviders = providerStore.providers.filter(p => p.provider_type === 'llm' && p.is_active)
  const providerId = defaultModels.value.default_optimize_provider_id || (llmProviders.length ? llmProviders[0].id : '')

  if (!providerId) {
    dialogMessages.value.push({ id: ++dialogMsgId, role: 'assistant', content: '请先在设置中配置LLM提供商' })
    return
  }

  try {
    let messageContent = userMsg
    if (currentAttachments.length) {
      const imageContexts = currentAttachments
        .filter(a => a.type.startsWith('image/'))
        .map(a => `[用户上传了图片: ${a.name}]`)
        .join('\n')
      const docContexts = currentAttachments
        .filter(a => !a.type.startsWith('image/') && a.content)
        .map(a => `\n[用户上传了文档: ${a.name}]\n${a.content}`)
        .join('\n')
      if (imageContexts) messageContent = imageContexts + '\n' + messageContent
      if (docContexts) messageContent = messageContent + '\n' + docContexts
    }

    const context = contextMode.value === 'shared' && currentSessionId.value
      ? messages.value.slice(-10).map(m => `${m.role === 'user' ? '用户' : '助手'}: ${m.content}`).join('\n') + '\n'
      : ''

    const userMsgId = ++dialogMsgId
    dialogMessages.value.push({ id: userMsgId, role: 'user', content: userMsg, attachments: currentAttachments })

    const responseHint = responseStyle.value === 'verbose'
      ? '请给出详细、全面的回答，展开解释每个要点。'
      : responseStyle.value === 'concise'
        ? '请给出极其简洁的回答，不要展开解释，直接给出核心信息。'
        : ''

    const systemPrompt = (contextMode.value === 'shared'
      ? '你是一个AI生图助手。你可以参考上下文中的对话来回答问题。请用中文回复。不要重复或总结上下文对话内容，直接回答用户当前问题。'
      : '你是一个AI生图助手。请根据用户输入回答问题。请用中文回复。') + responseHint

    const llmMessages: { role: string; content: string }[] = [
      { role: 'system', content: systemPrompt },
    ]
    const history = dialogMessages.value.slice(0, -1).slice(-20)
    for (const m of history) {
      llmMessages.push({ role: m.role, content: m.content })
    }
    llmMessages.push({ role: 'user', content: context + messageContent })

    const assistantMsgId = ++dialogMsgId
    dialogMessages.value.push({ id: assistantMsgId, role: 'assistant', content: '' })

    let fullContent = ''
    streamAbortController = new AbortController()
    if (searchEnabled.value) {
      dialogToolCalls.value = []
      const stream = promptApi.streamChatWithTools(llmMessages, providerId, ['web_search', 'image_search'], currentSessionId.value, 0.7, streamAbortController.signal)

      for await (const event of stream) {
        if (event.type === 'token') {
          fullContent += event.data as string
          const msg = dialogMessages.value.find(m => m.id === assistantMsgId)
          if (msg) msg.content = fullContent
        } else if (event.type === 'tool_call') {
          const tc = event.data as { name: string; args?: Record<string,unknown> }
          dialogToolCalls.value.push({ id: crypto.randomUUID(), name: tc.name, args: tc.args, content: '', collapsed: false })
        } else if (event.type === 'tool_result') {
          const tr = event.data as { name: string; content: string; meta?: Record<string,unknown> }
          const tool = dialogToolCalls.value.find(t => t.name === tr.name && !t.content)
          if (tool) tool.content = tr.content
        }
      }
    } else {
      const stream = promptApi.streamChat(llmMessages, providerId, currentSessionId.value, 0.7, streamAbortController.signal)

      for await (const token of stream) {
        fullContent += token
        const msg = dialogMessages.value.find(m => m.id === assistantMsgId)
        if (msg) msg.content = fullContent
      }
    }

    streamAbortController = null

    billingStore.fetchSummary()
    await store.fetchSessions()
  } catch (e: any) {
    dialogMessages.value.push({ id: ++dialogMsgId, role: 'assistant', content: '对话失败: ' + (e.message || '未知错误') })
  }
}

async function doOptimize() {
  if (!inputText.value.trim() || !selectedDirections.value.length || optimizing.value) return
  const sid = currentSessionId.value
  if (!sid) return
  optimizing.value = true
  optimizeResult.value = ''
  try {
    let directions = selectedDirections.value.filter(d => d !== 'custom').join(',')
    if (customInstruction.value) {
      directions = directions ? directions + ',custom:' + customInstruction.value : 'custom:' + customInstruction.value
    }
    const providerId = defaultModels.value.default_optimize_provider_id || ''
    if (!providerId) {
      const llmProviders = providerStore.providers.filter(p => p.provider_type === 'llm' && p.is_active)
      if (!llmProviders.length) {
        dialog.showAlert('请先在设置中配置LLM提供商')
        optimizing.value = false
        return
      }
      defaultModels.value.default_optimize_provider_id = llmProviders[0].id
    }

    let fullContent = ''
    streamAbortController = new AbortController()
    const stream = promptApi.optimizeStream(
      inputText.value,
      directions || 'detail_enhancement',
      defaultModels.value.default_optimize_provider_id || '',
      sid,
      streamAbortController.signal,
    )

    for await (const token of stream) {
      fullContent += token
      optimizeResult.value = fullContent
    }

    streamAbortController = null

    if (currentSessionId.value && fullContent && !fullContent.startsWith('优化失败')) {
      await sessionApi.addMessage(currentSessionId.value, {
        content: '提示词优化完成',
        message_type: 'optimization',
        metadata: { type: 'optimize', direction: directions, original: inputText.value, optimized: fullContent },
      })
    }

    billingStore.fetchSummary()
    await store.fetchSessions()
  } catch (e: any) {
    optimizeResult.value = '优化失败: ' + (e.message || '未知错误')
  } finally {
    optimizing.value = false
  }
}

function applyOptimizeResult() {
  if (optimizeResult.value && !optimizeResult.value.startsWith('优化失败')) {
    inputText.value = optimizeResult.value
  }
  optimizeResult.value = ''
}

async function doPlan() {
  if (!inputText.value.trim() || planning.value) return

  const providerId = defaultModels.value.default_plan_provider_id || ''
  if (!providerId) {
    const llmProviders = providerStore.providers.filter(p => p.provider_type === 'llm' && p.is_active)
    if (!llmProviders.length) {
      dialog.showAlert('请先在设置中配置LLM提供商')
      return
    }
    defaultModels.value.default_plan_provider_id = llmProviders[0].id
  }

  planning.value = true
  planStreamText.value = ''
  try {
    const optimizeDirs = selectedDirections.value.filter(d => d !== 'custom').join(', ') || '无'
    const hasRefs = attachments.value.some(a => a.type.startsWith('image/'))
    const size = noSizeLimit.value ? '不限' : `${imageWidth.value}x${imageHeight.value}`
    const strategyDesc = planStrategies.find(s => s.key === selectedPlanStrategy.value)?.desc || '并发生成'

    const systemPrompt = `你是一个AI图像生成任务规划师。根据用户的图像生成需求，将其分解为具体的子任务。

当前配置：
- 图像数量: ${imageCount.value}
- 图像尺寸: ${size}
- 优化方向: ${optimizeDirs}
- 参考图片: ${hasRefs ? '有' : '无'}
- 执行策略: ${strategyDesc}

对于每个子任务，请提供：
- prompt: 详细的图像生成提示词（英文，用于API调用）
- negative_prompt: 需要避免的元素
- description: 该步骤的中文说明
- image_count: 该步骤生成的图片数量（可选，默认为1）
- image_size: 该步骤的图片尺寸（可选，默认为${size}）

输出格式必须为JSON数组：
[
  {
    "prompt": "...",
    "negative_prompt": "...",
    "description": "...",
    "image_count": 1,
    "image_size": "${imageWidth.value}x${imageHeight.value}"
  }
]

规则：
1. prompt用英文撰写，要具体且描述性强
2. 包含风格、构图、光照和氛围细节
3. negative_prompt列出需要避免的常见问题
4. description用中文简要说明该步骤的目标
5. 将复杂需求分解为聚焦的子任务
6. ${selectedPlanStrategy.value === 'parallel' ? '各步骤应独立，可并发生成' : selectedPlanStrategy.value === 'iterative' ? '后续步骤应基于前一步结果进行优化' : '步骤按顺序执行'}
7. 只输出JSON数组，不要其他文字`

    let fullContent = ''
    streamAbortController = new AbortController()
    const stream = promptApi.planStream([
      { role: 'system', content: systemPrompt },
      { role: 'user', content: inputText.value },
    ], defaultModels.value.default_plan_provider_id || '', currentSessionId.value, 0.7, streamAbortController.signal)

    for await (const token of stream) {
      fullContent += token
      planStreamText.value = fullContent
    }

    streamAbortController = null

    try {
      let parsed = JSON.parse(fullContent)
      if (typeof parsed === 'object' && 'sub_tasks' in parsed) {
        parsed = parsed.sub_tasks
      }
      if (!Array.isArray(parsed)) parsed = [parsed]
      planSteps.value = parsed.map((st: any) => ({
        prompt: st.prompt || '',
        negative_prompt: st.negative_prompt || '',
        description: st.description || '',
        image_count: st.image_count || 1,
        image_size: st.image_size || '',
      })).filter((st: any) => st.prompt)
    } catch {
      planSteps.value = [{ prompt: fullContent, negative_prompt: '', description: '', image_count: 1 }]
    }

    if (planSteps.value.length === 0) {
      dialog.showAlert('规划失败：未能生成有效的步骤，请尝试更详细的描述')
    }

    if (currentSessionId.value && planSteps.value.length > 0) {
      const stepsText = planSteps.value.map((s, i) => `步骤${i + 1}: ${s.prompt}${s.negative_prompt ? '\n反向提示: ' + s.negative_prompt : ''}`).join('\n\n')
      await sessionApi.addMessage(currentSessionId.value, {
        content: `任务规划: ${inputText.value}`,
        message_type: 'plan',
        metadata: { type: 'plan', steps: planSteps.value.map((s, i) => ({ prompt: s.prompt, negative_prompt: s.negative_prompt, description: s.description })), description: inputText.value },
      })
    }

    await store.fetchSessions()
    billingStore.fetchSummary()
  } catch (e: any) {
    dialog.showAlert('规划失败: ' + (e.message || '未知错误'))
    planSteps.value = []
  } finally {
    planning.value = false
    planStreamText.value = ''
  }
}

function moveStep(index: number, direction: number) {
  const target = index + direction
  if (target < 0 || target >= planSteps.value.length) return
  const steps = [...planSteps.value]
  ;[steps[index], steps[target]] = [steps[target], steps[index]]
  planSteps.value = steps
}

function duplicateStep(index: number) {
  const step = planSteps.value[index]
  planSteps.value.splice(index + 1, 0, { ...step, description: (step.description || '') + ' (副本)' })
}

const planCheckpoint = ref<{ stepIndex: number; message: string } | null>(null)
let planCheckpointResolve: (() => void) | null = null

async function executePlan() {
  const sid = currentSessionId.value
  if (!sid) return
  const steps = planSteps.value.filter(s => s.prompt)
  if (!steps.length) return

  const strategy = selectedPlanStrategy.value
  activeTasks.value.set(sid, {
    sessionId: sid,
    type: 'plan',
    status: 'running',
    progress: 0,
    total: steps.length,
    abortController: null,
  })
  generatingText.value = '规划执行中...'

  const errors: string[] = []
  let completed = 0

  let lastStepImageUrls: string[] = []

  const initialRefs: string[] = []
  for (const img of contextImageList.value) {
    if (img.preview && img.source === 'upload') {
      initialRefs.push(img.preview)
    } else if (img.source === 'refine' || img.source === 'context') {
      const base64 = await fetchImageAsBase64(img.url)
      if (base64) initialRefs.push(base64)
    }
  }

  async function runStep(step: PlanStep, index: number, referenceImages?: string[]) {
    try {
      const ctxUrls = contextImageList.value
        .filter(img => img.source === 'context')
        .map(img => img.url)
      const ctxMsgs = messages.value.slice(-10).map(m => {
        const entry: { role: string; content: string; image_urls?: string[] } = {
          role: m.role,
          content: m.content,
        }
        if (m.message_type === 'image' && m.metadata?.image_urls && ctxUrls.length) {
          const urls = (m.metadata.image_urls as string[]).filter(url => ctxUrls.includes(url))
          if (urls.length) entry.image_urls = urls
        }
        return entry
      })
      const refLabels = (referenceImages || []).map((_, i) => ({
        index: i + 1,
        source: 'refine' as const,
        name: `步骤${index + 1}参考图${i + 1}`,
      }))
      const result = await store.generate(sid, {
        prompt: step.prompt,
        negative_prompt: step.negative_prompt,
        image_count: step.image_count || imageCount.value,
        image_size: step.image_size || (noSizeLimit.value ? undefined : `${imageWidth.value}x${imageHeight.value}`),
        plan_strategy: strategy,
        reference_images: referenceImages,
        context_messages: ctxMsgs.length ? ctxMsgs : undefined,
        reference_labels: refLabels.length ? refLabels : undefined,
      })
      if (result?.image_urls?.length) {
        lastStepImageUrls = result.image_urls
      }
    } catch (e: any) {
      errors.push(`步骤${index + 1}失败: ${e.message || '未知错误'}`)
    } finally {
      completed++
      const task = activeTasks.value.get(sid)
      if (task) task.progress = completed
    }
  }

  async function runStepWithCheckpoint(step: PlanStep, index: number, referenceImages?: string[]) {
    await runStep(step, index, referenceImages)
    if (step.checkpoint?.enabled) {
      planCheckpoint.value = {
        stepIndex: index,
        message: step.checkpoint.message || `步骤${index + 1}已完成，请确认后继续`,
      }
      await new Promise<void>((resolve) => { planCheckpointResolve = resolve })
      planCheckpoint.value = null
      planCheckpointResolve = null
    }
  }

  if (strategy === 'parallel') {
    const concurrency = Math.min(defaultModels.value.max_concurrent, steps.length)
    let nextIndex = 0
    const workers: Promise<void>[] = []
    for (let i = 0; i < concurrency && nextIndex < steps.length; i++) {
      workers.push((async () => {
        while (nextIndex < steps.length) {
          const idx = nextIndex++
          await runStepWithCheckpoint(steps[idx], idx, initialRefs.length ? initialRefs : undefined)
        }
      })())
    }
    await Promise.all(workers)
  } else if (strategy === 'iterative') {
    for (let i = 0; i < steps.length; i++) {
      const task = activeTasks.value.get(sid)
      if (task) generatingText.value = `迭代 ${i + 1}/${steps.length}`
      let refs: string[] | undefined
      if (i === 0 && initialRefs.length) {
        refs = initialRefs
      } else if (i > 0 && lastStepImageUrls.length) {
        const base64 = await fetchImageAsBase64(lastStepImageUrls[0])
        if (base64) refs = [base64]
      }
      await runStepWithCheckpoint(steps[i], i, refs)
    }
  } else {
    for (let i = 0; i < steps.length; i++) {
      const task = activeTasks.value.get(sid)
      if (task) generatingText.value = `步骤 ${i + 1}/${steps.length}`
      await runStepWithCheckpoint(steps[i], i, initialRefs.length ? initialRefs : undefined)
    }
  }

  const task = activeTasks.value.get(sid)
  if (task) task.status = 'done'
  setTimeout(() => activeTasks.value.delete(sid), 3000)
  planSteps.value = []
  billingStore.fetchSummary()
  await store.fetchSessions()
  if (errors.length) {
    dialog.showAlert(`部分步骤执行失败:\n${errors.join('\n')}`)
  }
}

function continuePlan() {
  planCheckpointResolve?.()
  planCheckpointResolve = null
}

function abortPlan() {
  const sid = currentSessionId.value
  if (sid) {
    const task = activeTasks.value.get(sid)
    if (task) task.status = 'done'
    setTimeout(() => activeTasks.value.delete(sid), 1000)
  }
  planCheckpoint.value = null
  planCheckpointResolve = null
  planSteps.value = []
}

async function saveAsTemplate() {
  const steps = planSteps.value.filter(s => s.prompt)
  if (!steps.length) {
    dialog.showAlert('没有可保存的步骤')
    return
  }
  const name = await dialog.showPrompt('模板名称', '输入模板名称')
  if (!name) return

  // 自动扫描 {{xxx}} 变量
  const varSet = new Set<string>()
  for (const step of steps) {
    const matches = (step.prompt + ' ' + step.negative_prompt).matchAll(/\{\{(\w+)\}\}/g)
    for (const m of matches) {
      varSet.add(m[1])
    }
  }

  // 检测重复短语（出现在 2 个以上步骤中的 3 词以上短语）
  const promptWords = steps.map(s => s.prompt)
  const phraseCount: Record<string, number> = {}
  for (const p of promptWords) {
    const words = p.split(/\s+/)
    for (let len = 3; len <= Math.min(6, words.length); len++) {
      for (let i = 0; i <= words.length - len; i++) {
        const phrase = words.slice(i, i + len).join(' ')
        phraseCount[phrase] = (phraseCount[phrase] || 0) + 1
      }
    }
  }
  const repeatedPhrases = Object.entries(phraseCount)
    .filter(([, count]) => count >= 2)
    .sort((a, b) => b[0].length - a[0].length)
    .slice(0, 3)
    .map(([phrase]) => phrase)

  // 构建 variables 数组
  const variables = Array.from(varSet).map(key => ({
    key,
    type: 'string' as const,
    label: key,
    default: '',
  }))

  // 如果发现重复短语且没有已有变量覆盖，提示用户
  let description = ''
  if (repeatedPhrases.length && !varSet.size) {
    description = `检测到重复短语: ${repeatedPhrases.join(', ')}。可在模板管理中将其替换为 {{变量名}} 占位符。`
  }

  try {
    await planTemplateApi.create({
      name,
      description,
      strategy: selectedPlanStrategy.value,
      steps: steps.map(({ prompt, negative_prompt, description, image_count, image_size }) => ({
        prompt, negative_prompt, description, image_count: image_count || 1, image_size: image_size || '',
      })),
      variables,
    } as any)
    const { data } = await planTemplateApi.list()
    planTemplates.value = data
    const varMsg = variables.length ? `\n已自动识别 ${variables.length} 个变量: ${variables.map(v => '{{' + v.key + '}}').join(', ')}` : ''
    const phraseMsg = repeatedPhrases.length ? `\n检测到重复短语，建议在模板管理中替换为变量` : ''
    dialog.showAlert('模板保存成功' + varMsg + phraseMsg)
  } catch (e: any) {
    dialog.showAlert('保存失败: ' + (e.message || '未知错误'))
  }
}

function showContextMenu(e: MouseEvent, session: any) {
  if (contextMenuTimer) clearTimeout(contextMenuTimer)
  contextMenu.value = { show: true, x: e.clientX, y: e.clientY, sessionId: session.id }
  contextMenuTimer = setTimeout(() => { contextMenu.value.show = false }, 3000)
}

function showImageContextMenu(e: MouseEvent, url: string) {
  if (contextMenuTimer) clearTimeout(contextMenuTimer)
  imageContextMenu.value = { show: true, x: e.clientX, y: e.clientY, url }
  contextMenuTimer = setTimeout(() => { imageContextMenu.value.show = false }, 3000)
}

function isContextPinned(url: string): boolean {
  return contextImageUrls.value.has(url)
}

function toggleContextPin(url: string) {
  if (contextImageUrls.value.has(url)) {
    const idx = contextImageList.value.findIndex(x => x.url === url)
    if (idx >= 0) contextImageList.value.splice(idx, 1)
  } else {
    contextImageList.value.push({ url, source: 'context', name: '已固定' })
  }
  imageContextMenu.value.show = false
}

async function renameSession(id: string) {
  const title = await dialog.showPrompt('输入新名称:')
  if (title) await store.renameSession(id, title)
  contextMenu.value.show = false
}

async function deleteSession(id: string) {
  if (await dialog.showConfirm('删除此会话？')) await store.deleteSession(id)
  contextMenu.value.show = false
}

watch(selectedSkillIds, (ids) => {
  store.selectedSkillIds = ids
})
</script>

<style scoped>
.session-page {
  display: flex;
  height: calc(100vh - var(--topbar-height));
}

.session-list {
  width: 200px;
  border-right: 1px solid var(--border);
  background: var(--card);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.2s ease;
}

.session-list.collapsed {
  width: 40px;
}

.session-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px 8px 12px;
  border-bottom: 1px solid var(--border);
  min-height: 40px;
}

.session-list.collapsed .session-list-header {
  justify-content: center;
  padding: 8px;
}

.session-list-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.session-list-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: none;
  background: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius);
  flex-shrink: 0;
}

.session-list-toggle:hover {
  background: var(--hover);
  color: var(--text);
}

.new-session-btn {
  margin: 10px 12px 8px;
  width: calc(100% - 24px);
}

.session-items {
  flex: 1;
  overflow-y: auto;
}

.session-item {
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}

.session-item:hover {
  background: var(--hover);
}

.session-item.active {
  background: var(--active);
}

.session-title {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.session-title-row .session-title {
  margin-bottom: 0;
  flex: 1;
  min-width: 0;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 2px;
  white-space: nowrap;
  flex-shrink: 0;
}

.status-badge.generating {
  background: #000;
  color: #fff;
}

.status-badge.optimizing,
.status-badge.planning {
  background: #E5E5E5;
  color: #000;
}

.status-badge.error {
  background: #000;
  color: #fff;
}

.task-progress {
  font-size: 10px;
  color: var(--text-secondary);
}

.icon-spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.session-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-secondary);
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.message {
  margin-bottom: 12px;
}

.message.user {
  display: flex;
  justify-content: flex-end;
}

.message.user .message-content {
  background: var(--hover);
  color: var(--text);
  border-radius: 12px 12px 2px 12px;
  padding: 8px 14px;
  max-width: 70%;
}

.message.assistant .message-content,
.message.system .message-content {
  max-width: 85%;
}

.message.assistant p,
.message.system p {
  font-size: 13px;
  line-height: 1.6;
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
  margin-top: 8px;
}

.image-item {
  position: relative;
  border-radius: var(--radius);
  overflow: hidden;
  border: 1px solid var(--border);
}

.image-item img {
  width: 100%;
  display: block;
  cursor: pointer;
}

.image-check {
  position: absolute;
  top: 4px;
  left: 4px;
}

.image-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.optimization-compare {
  display: flex;
  gap: 12px;
  margin: 8px 0;
}

.compare-side {
  flex: 1;
}

.compare-label {
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 4px;
  font-weight: 500;
}

.compare-text {
  font-size: 12px;
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius);
  line-height: 1.5;
}

.compare-text.optimized {
  background: #F0F0F0;
  font-weight: 500;
}

.plan-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  margin-top: 4px;
}

.plan-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  background: var(--hover);
  transition: background 0.15s;
}

.plan-card-header:hover {
  background: var(--border);
}

.plan-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
}

.plan-card-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.plan-step-count {
  font-size: 11px;
  color: #888;
}

.plan-chevron {
  transition: transform 0.2s;
  color: #888;
}

.plan-chevron.expanded {
  transform: rotate(180deg);
}

.plan-card-body {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
}

.plan-card-step {
  border-bottom: 1px solid var(--border);
  padding: 8px 0;
}

.plan-card-step:last-child {
  border-bottom: none;
}

.plan-step-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
}

.step-prompt-preview {
  line-height: 1.5;
  color: #555;
  flex: 1;
}

.plan-step-detail {
  display: none;
  margin-top: 8px;
  padding-left: 26px;
}

.plan-card-step:hover .plan-step-detail {
  display: block;
}

.step-field {
  margin-bottom: 6px;
}

.step-field:last-child {
  margin-bottom: 0;
}

.step-field label {
  font-size: 10px;
  text-transform: uppercase;
  color: #999;
  letter-spacing: 0.5px;
  display: block;
  margin-bottom: 2px;
}

.step-field p {
  font-size: 12px;
  line-height: 1.5;
  padding: 6px 8px;
  background: var(--hover);
  border-radius: 4px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.step-desc {
  font-size: 12px;
  color: #666;
  margin: 4px 0 0;
  padding: 4px 8px;
  background: var(--hover);
  border-radius: 4px;
  line-height: 1.5;
}

.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent);
  color: var(--card);
  font-size: 10px;
  flex-shrink: 0;
}

.step-text {
  line-height: 1.5;
}

.error-text {
  color: var(--danger);
}

.agent-card {
  border-left: 3px solid var(--accent);
  background: var(--bg, #fafafa);
  padding: 12px;
  margin: 4px 0;
  border-radius: 0 var(--radius) var(--radius) 0;
}

.agent-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.agent-badge {
  background: var(--accent);
  color: #fff;
  padding: 1px 8px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 500;
}

.agent-cost {
  font-size: 11px;
  color: var(--text-secondary);
}

.agent-steps {
  margin-bottom: 8px;
}

.agent-step {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.agent-step-icon {
  font-size: 10px;
  width: 16px;
  text-align: center;
}

.agent-card-content {
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
}

.attachment-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.attachment-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--hover);
  border-radius: var(--radius);
  font-size: 11px;
}

.attachment-thumb {
  width: 24px;
  height: 24px;
  object-fit: cover;
  border-radius: 2px;
}

.attachment-doc {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--border);
  border-radius: 2px;
}

.doc-icon {
  font-size: 8px;
  font-weight: 600;
  color: var(--text-secondary);
}

.attachment-name {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.refine-strip {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 8px;
  flex-wrap: wrap;
  min-height: 32px;
}

.refine-strip-item {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.refine-strip-thumb {
  width: 36px;
  height: 36px;
  object-fit: cover;
  border-radius: 3px;
  border: 1px solid var(--border);
}

.refine-strip-thumb-wrap {
  position: relative;
  width: 36px;
  height: 36px;
}

.refine-strip-badge {
  position: absolute;
  top: -4px;
  left: -4px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent);
  color: white;
  font-size: 9px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}

.refine-strip-label {
  font-size: 9px;
  color: var(--text-secondary);
  max-width: 48px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
}

.refine-add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px dashed var(--border);
  border-radius: 3px;
  cursor: pointer;
  font-size: 10px;
  color: var(--text-secondary);
}

.refine-add-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.refine-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  background: #f0f0f0;
  border-bottom: 1px solid var(--border);
}

.refine-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
}

.attachment-remove {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--danger);
  color: white;
  border: none;
  font-size: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.upload-btn:hover {
  background: var(--hover);
  color: var(--accent);
  border-color: var(--accent);
}

.message-content.generating {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--hover);
  border-radius: 12px;
}

.generating-indicator {
  display: flex;
  gap: 4px;
}

.generating-indicator .dot {
  width: 6px;
  height: 6px;
  background: var(--text-secondary);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.generating-indicator .dot:nth-child(1) {
  animation-delay: -0.32s;
}

.generating-indicator .dot:nth-child(2) {
  animation-delay: -0.16s;
}

.generating-indicator .dot:nth-child(3) {
  animation-delay: 0s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

.generating-text {
  font-size: 13px;
  color: var(--text-secondary);
}

.compare-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
}

.lightbox-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.85);
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.lightbox-content {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: default;
}

.lightbox-close {
  position: absolute;
  top: -40px;
  right: 0;
  background: none;
  border: none;
  color: #fff;
  cursor: pointer;
  padding: 4px;
  opacity: 0.7;
  transition: opacity 0.15s;
}

.lightbox-close:hover {
  opacity: 1;
}

.lightbox-img {
  max-width: 90vw;
  max-height: 80vh;
  border-radius: 4px;
  object-fit: contain;
}

.lightbox-actions {
  margin-top: 12px;
  display: flex;
  gap: 8px;
}

.compare-view {
  background: var(--card);
  border-radius: 8px;
  padding: 24px;
  max-width: 90vw;
  max-height: 90vh;
  overflow: auto;
}

.compare-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.compare-images {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.compare-img {
  max-width: 300px;
  max-height: 400px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
}

.input-area {
  border-top: 1px solid var(--border);
  padding: 12px 16px;
  background: var(--card);
}

.input-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-area textarea {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  resize: none;
  font-size: 13px;
  outline: none;
  min-height: 60px;
  max-height: 200px;
  overflow-y: auto;
  transition: height 0.1s ease;
}

.input-area textarea:focus {
  border-color: var(--accent);
}

.negative-input {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 12px;
  font-size: 12px;
  outline: none;
  color: var(--text-secondary);
}

.negative-input:focus {
  border-color: var(--accent);
}

.input-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}

.input-options {
  display: flex;
  align-items: center;
  gap: 4px;
}

.option-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.count-btn {
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  font-size: 12px;
  cursor: pointer;
}

.count-btn.active {
  background: var(--accent);
  color: var(--card);
  border-color: var(--accent);
}

.size-label {
  margin-left: 8px;
}

.size-input {
  width: 60px;
  padding: 2px 4px;
  font-size: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-align: center;
}

.size-input:focus {
  outline: none;
  border-color: var(--accent);
}

.size-sep {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0 2px;
}

.no-limit-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: 8px;
  cursor: pointer;
}

.no-limit-label input[type="checkbox"] {
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.input-actions {
  display: flex;
  gap: 6px;
}

.assistant-sidebar {
  width: 320px;
  border-left: 1px solid var(--border);
  background: var(--card);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.2s ease;
}

.assistant-sidebar.expanded {
  width: 520px;
}

.assistant-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  min-height: 40px;
}

.assistant-header-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  align-items: center;
}

.assistant-tabs {
  display: flex;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.tab-btn {
  padding: 4px 8px;
  border: none;
  background: none;
  font-size: 12px;
  cursor: pointer;
  border-radius: var(--radius);
  color: var(--text-secondary);
  white-space: nowrap;
}

.tab-btn.active {
  background: var(--active);
  color: var(--text);
  font-weight: 500;
}

.assistant-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
}

.context-toggle {
  display: flex;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  flex-shrink: 0;
}

.toggle-btn {
  flex: 1;
  padding: 6px;
  border: none;
  background: var(--card);
  font-size: 12px;
  cursor: pointer;
}

.toggle-btn.active {
  background: var(--accent);
  color: var(--card);
}

.dialog-config-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  margin-bottom: 0;
}

.dialog-config-bar .context-toggle {
  flex: 1;
}

.dialog-settings-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--card);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
  padding: 0;
}

.dialog-settings-btn:hover {
  background: var(--hover);
  color: var(--accent);
  border-color: var(--accent);
}

.dialog-settings-btn.active {
  background: var(--accent);
  color: var(--card);
  border-color: var(--accent);
}

.dialog-settings-panel {
  flex-shrink: 0;
  margin-top: 6px;
  margin-bottom: 2px;
}

.tab-dialog {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.dialog-messages {
  flex: 1;
  overflow-y: auto;
  margin-bottom: 12px;
  min-height: 100px;
}

.dialog-msg {
  padding: 6px 8px;
  margin-bottom: 4px;
  border-radius: var(--radius);
  font-size: 12px;
  line-height: 1.5;
}

.dialog-msg.user {
  background: var(--hover);
  text-align: right;
}

.dialog-msg.assistant {
  background: var(--active);
  position: relative;
}

.dialog-msg-content {
  white-space: pre-wrap;
  word-break: break-word;
}

.dialog-msg-copy {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 20px;
  height: 20px;
  padding: 2px;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}

.dialog-msg:hover .dialog-msg-copy {
  opacity: 0.6;
}

.dialog-msg-copy:hover {
  opacity: 1 !important;
  background: var(--hover);
}

.dialog-actions {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.msg-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 4px;
}

.msg-attachment-thumb {
  width: 40px;
  height: 40px;
  object-fit: cover;
  border-radius: 4px;
}

.dialog-input-area {
  flex-shrink: 0;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  margin-top: auto;
}

.dialog-attachment-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.dialog-attachment-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: var(--hover);
  border-radius: var(--radius);
  font-size: 10px;
}

.dialog-attachment-thumb {
  width: 20px;
  height: 20px;
  object-fit: cover;
  border-radius: 2px;
}

.dialog-attachment-doc {
  font-size: 10px;
  color: var(--text-secondary);
}

.dialog-attachment-remove {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--danger);
  color: white;
  border: none;
  font-size: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.dialog-input-row {
  display: flex;
  gap: 6px;
  align-items: center;
}

.dialog-input-row input,
.dialog-textarea {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 12px;
  outline: none;
  font-family: inherit;
  resize: none;
  line-height: 1.4;
}

.dialog-input-row input:focus,
.dialog-textarea:focus {
  border-color: var(--accent);
}

.dialog-upload-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.dialog-upload-btn:hover {
  background: var(--hover);
  color: var(--accent);
  border-color: var(--accent);
}

.search-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: transparent;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}

.search-toggle-btn:hover {
  background: var(--hover);
  color: var(--accent);
}

.search-toggle-btn.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.tool-calls-area {
  padding: 4px 8px;
}

.tool-call-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin: 4px 0;
  overflow: hidden;
  background: var(--bg, #fafafa);
}

.tool-call-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 12px;
}

.tool-call-badge {
  background: #e8e8e8;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 11px;
}

.tool-call-status {
  color: var(--text-secondary);
  font-size: 11px;
}

.tool-call-body {
  padding: 6px 10px;
  border-top: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-secondary);
  max-height: 150px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.tool-call-loading {
  color: var(--accent);
  animation: pulse-text 1.5s ease-in-out infinite;
}

@keyframes pulse-text {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.section-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.direction-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 0;
  cursor: pointer;
}

.direction-info {
  display: flex;
  flex-direction: column;
}

.direction-name {
  font-size: 13px;
  font-weight: 500;
}

.direction-desc {
  font-size: 11px;
  color: var(--text-secondary);
}

.custom-input {
  margin-top: 6px;
}

.preview-text, .result-text, .stream-text {
  font-size: 12px;
  padding: 8px;
  background: var(--hover);
  border-radius: var(--radius);
  line-height: 1.5;
  margin-bottom: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

.plan-streaming {
  margin-bottom: 12px;
}

.plan-streaming .stream-text {
  max-height: 200px;
  overflow-y: auto;
  border-left: 2px solid var(--accent);
  padding-left: 8px;
  animation: pulse-border 1.5s ease-in-out infinite;
}

@keyframes pulse-border {
  0%, 100% { border-left-color: var(--accent); }
  50% { border-left-color: transparent; }
}

.optimize-result .result-text {
  border-left: 2px solid var(--accent);
  padding-left: 8px;
  transition: border-left-color 0.3s;
}

.optimize-result .result-text.streaming {
  animation: pulse-border 1.5s ease-in-out infinite;
}

.plan-step {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px;
  margin-bottom: 8px;
}

.step-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 500;
}

.step-actions {
  display: flex;
  gap: 4px;
}

.btn-icon {
  background: none;
  border: 1px solid var(--border);
  border-radius: 2px;
  cursor: pointer;
  font-size: 12px;
  padding: 1px 5px;
  color: var(--text);
}

.btn-icon:hover {
  background: var(--hover);
}

.btn-icon:disabled {
  opacity: 0.3;
  cursor: default;
}

.plan-template-section {
  margin-bottom: 10px;
}

.template-select {
  width: 100%;
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-size: 13px;
  background: #fff;
}

.template-variables {
  margin-bottom: 10px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.plan-strategy {
  margin-bottom: 12px;
}

.strategy-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.strategy-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 12px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.strategy-label:has(input:checked) {
  background: var(--active);
  border-color: var(--accent);
}

.strategy-desc {
  color: var(--text-secondary);
  font-size: 10px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-row label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}

.plan-summary {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 8px 0;
}

.skill-item {
  margin-bottom: 8px;
}

.skill-label {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  cursor: pointer;
}

.skill-info {
  display: flex;
  flex-direction: column;
}

.skill-name {
  font-size: 13px;
  font-weight: 500;
}

.skill-desc {
  font-size: 11px;
  color: var(--text-secondary);
}

.empty-hint {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: center;
  padding: 20px 0;
}

.hint-text {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 12px;
}

.checkpoint-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.checkpoint-card {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 24px;
  max-width: 360px;
  width: 90%;
  text-align: center;
}

.checkpoint-card p {
  margin: 0 0 16px 0;
  font-size: 14px;
}

.checkpoint-actions {
  display: flex;
  gap: 8px;
  justify-content: center;
}

.context-menu {
  position: fixed;
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  z-index: 300;
  padding: 4px;
}

.context-menu button {
  display: block;
  width: 100%;
  padding: 6px 12px;
  border: none;
  background: none;
  text-align: left;
  font-size: 12px;
  cursor: pointer;
  border-radius: var(--radius);
}

.context-menu button:hover {
  background: var(--hover);
}
</style>
