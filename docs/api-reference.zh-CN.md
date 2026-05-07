# LamImager API 参考

基础 URL: `http://localhost:8000/api`

## 认证

无（单用户桌面应用）。

## 通用响应格式

### 成功
```json
{
  "id": "uuid-string",
  "field1": "value1",
  "created_at": "2026-05-06T12:00:00"
}
```

### 错误
```json
{
  "detail": "错误信息"
}
```

---

## 会话

### 列出会话
```
GET /api/sessions
```

响应: `Session[]`

```json
[
  {
    "id": "uuid",
    "title": "新会话",
    "created_at": "2026-05-07T12:00:00",
    "updated_at": "2026-05-07T12:00:00",
    "message_count": 5,
    "cost": 0.15,
    "tokens": 1234
  }
]
```

### 创建会话
```
POST /api/sessions
```

请求体:
```json
{
  "title": "我的会话"
}
```

响应: `Session`

### 获取会话
```
GET /api/sessions/{id}
```

响应: `Session`

### 更新会话
```
PUT /api/sessions/{id}
```

请求体:
```json
{
  "title": "更新后的标题"
}
```

### 删除会话
```
DELETE /api/sessions/{id}
```

### 获取会话消息
```
GET /api/sessions/{id}/messages
```

响应: `Message[]`

```json
[
  {
    "id": "uuid",
    "session_id": "uuid",
    "role": "user",
    "content": "生成一只猫",
    "message_type": "text",
    "metadata": {},
    "created_at": "2026-05-07T12:00:00"
  }
]
```

### 添加消息到会话
```
POST /api/sessions/{id}/messages
```

请求体:
```json
{
  "content": "消息文本",
  "message_type": "text",
  "metadata": {}
}
```

消息类型: `text` | `image` | `optimization` | `plan` | `skill` | `error`

规划消息的 metadata:
```json
{
  "type": "plan",
  "steps": [
    {"prompt": "英文提示词用于 API", "negative_prompt": "...", "description": "中文步骤描述"}
  ],
  "description": "原始用户输入"
}
```

响应: `Message`

### 在会话中生成图片
```
POST /api/sessions/{id}/generate
```

请求体:
```json
{
  "prompt": "一只毛茸茸的猫坐在椅子上",
  "negative_prompt": "模糊, 低质量",
  "image_count": 1,
  "image_size": "1024x1024",
  "skill_ids": [],
  "optimize_directions": ["detail_enhancement"],
  "custom_optimize_instruction": "",
  "reference_images": ["data:image/png;base64,..."],
  "context_messages": [{"role": "user", "content": "..."}]
}
```

响应: `Message` (包含生成图片的助手消息)

---

## 设置

### 获取默认模型
```
GET /api/settings/default-models
```

响应:
```json
{
  "default_image_provider_id": "uuid",
  "default_llm_provider_id": "uuid",
  "default_optimize_provider_id": "uuid",
  "default_plan_provider_id": "uuid",
  "default_skill_id": "uuid",
  "default_image_width": 1024,
  "default_image_height": 1024
}
```

### 更新默认模型
```
PUT /api/settings/default-models
```

请求体:
```json
{
  "default_image_provider_id": "uuid",
  "default_llm_provider_id": "uuid"
}
```

---

## 提供商

### 列出提供商
```
GET /api/providers
```

查询参数:
- `provider_type` (可选): `image_gen` | `llm`

响应: `ApiProvider[]`

### 创建提供商
```
POST /api/providers
```

请求体:
```json
{
  "nickname": "OpenAI GPT-4",
  "base_url": "https://api.openai.com",
  "model_id": "gpt-4o",
  "api_key": "sk-xxxxx",
  "provider_type": "llm",
  "billing_type": "per_token",
  "unit_price": 0.01,
  "currency": "USD",
  "is_active": true
}
```

响应: `ApiProvider` (api_key 显示为 `****xxxx`)

### 获取提供商
```
GET /api/providers/{id}
```

响应: `ApiProvider`

### 更新提供商
```
PUT /api/providers/{id}
```

请求体: 部分 `ApiProviderCreate` (省略 `api_key` 则保留当前值)

响应: `ApiProvider`

### 删除提供商
```
DELETE /api/providers/{id}
```

响应: `{"message": "Provider deleted"}`

### 测试连接
```
POST /api/providers/{id}/test
```

响应:
```json
{
  "success": true,
  "message": "连接成功"
}
```

---

## 技能

### 列出技能
```
GET /api/skills
```

响应: `Skill[]`

### 创建技能
```
POST /api/skills
```

请求体:
```json
{
  "name": "产品摄影",
  "description": "专业产品拍摄风格",
  "prompt_template": "Professional product photo of {subject}, studio lighting, white background, {prompt}",
  "parameters": {"subject": "product"},
  "is_builtin": false
}
```

响应: `Skill`

### 导入技能
```
POST /api/skills/import
```

请求体: 与创建技能相同

响应: `Skill`

### 更新/删除技能
```
PUT /api/skills/{id}
DELETE /api/skills/{id}
```

---

## 规则

### 列出规则
```
GET /api/rules
```

查询参数:
- `rule_type` (可选): `default_params` | `filter` | `workflow`

响应: `Rule[]`

### 创建规则
```
POST /api/rules
```

请求体:
```json
{
  "name": "默认负面提示词",
  "rule_type": "filter",
  "config": {
    "negative_keywords": ["模糊", "低质量", "水印"]
  },
  "is_active": true,
  "priority": 10
}
```

响应: `Rule`

### 切换规则激活状态
```
PUT /api/rules/{id}/toggle
```

响应: `Rule`

---

## 账单

### 获取汇总
```
GET /api/billing/summary
```

响应:
```json
{
  "today": 1.23,
  "month": 45.67,
  "total": 123.45,
  "currency": "CNY"
}
```

### 获取详情
```
GET /api/billing/details
```

查询参数:
- `start_date`: ISO 日期字符串
- `end_date`: ISO 日期字符串
- `provider_id`: UUID
- `session_id`: UUID
- `page`: int (默认 1)
- `page_size`: int (默认 20)

响应:
```json
{
  "total": 100,
  "page": 1,
  "page_size": 20,
  "records": [BillingRecord]
}
```

### 导出 CSV
```
GET /api/billing/export
```

查询参数:
- `start_date`, `end_date`

响应: `text/csv` 附件

---

## 参考图

### 列出参考图
```
GET /api/references
```

查询参数:
- `is_global`: boolean

响应: `ReferenceImage[]`

### 上传参考图
```
POST /api/references/upload
```

Content-Type: `multipart/form-data`

表单字段:
- `file`: File
- `name`: string
- `is_global`: boolean
- `strength`: float (0-1)

响应: `ReferenceImage`

### 更新参考图
```
PUT /api/references/{id}
```

请求体:
```json
{
  "name": "新名称",
  "is_global": true,
  "strength": 0.7,
  "crop_config": {"x": 0, "y": 0, "width": 100, "height": 100}
}
```

---

## 提示词优化

### 优化提示词
```
POST /api/prompt/optimize
```

请求体:
```json
{
  "prompt": "一只猫坐在椅子上",
  "direction": "detail_enhancement",
  "llm_provider_id": "uuid"
}
```

方向: `detail_enhancement` | `style_unification` | `composition_optimization`

响应:
```json
{
  "original": "一只猫坐在椅子上",
  "optimized": "一只毛茸茸的三花猫优雅地栖息在复古木椅上，午后柔和的阳光透过蕾丝窗帘洒落，浅景深，暖色调，照片级真实风格",
  "direction": "detail_enhancement"
}
```

### 流式 LLM 对话
```
POST /api/prompt/stream
```

Content-Type: `text/event-stream` (SSE)

请求体:
```json
{
  "messages": [{"role": "user", "content": "你好"}],
  "provider_id": "uuid",
  "temperature": 0.7
}
```

SSE 事件:
- `data: {"token": "词"}` - 每个生成的 token
- `data: {"done": true, "cost": 0.001}` - 完成事件，包含账单
- `data: {"error": "信息"}` - 错误事件

---

## 仪表盘

### 获取统计
```
GET /api/dashboard/stats
```

响应:
```json
{
  "total_sessions": 10,
  "total_images": 35,
  "total_generations": 7,
  "monthly_cost": 12.34
}
```

---

## 健康检查

```
GET /api/health
```

响应:
```json
{
  "status": "ok",
  "version": "0.1.0"
}
```
