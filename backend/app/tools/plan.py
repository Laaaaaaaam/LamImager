from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.plan_template_service import (
    list_templates,
    get_template,
    create_template,
    apply_template,
)
from app.schemas.plan_template import PlanTemplateCreate, PlanTemplateApplyRequest, PlanStepSchema, TemplateVariableSchema
from app.tools.base import Tool, ToolResult


class PlanTool(Tool):
    name = "plan"
    description = (
        "管理和使用生图计划模板。支持四种操作：\n"
        "1. list — 列出所有可用模板，供判断是否可复用\n"
        "2. apply — 应用指定模板并填充变量，获得可执行的步骤列表\n"
        "3. create — 将当前生成的计划保存为新模板，方便以后复用\n"
        "4. generate — 根据需求生成一个新的计划（步骤列表），不依赖已有模板"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "apply", "create", "generate"],
                "description": "操作类型：list=列出模板, apply=应用模板, create=保存模板, generate=生成新计划",
            },
            "template_id": {
                "type": "string",
                "description": "模板ID，action=apply时必填",
            },
            "variables": {
                "type": "object",
                "description": "变量键值对，action=apply时用于填充模板中的{{变量}}占位符",
            },
            "name": {
                "type": "string",
                "description": "新模板名称，action=create时必填",
            },
            "description": {
                "type": "string",
                "description": "新模板描述，action=create时选填",
            },
            "steps": {
                "type": "array",
                "items": {"type": "object"},
                "description": "步骤列表，action=create时必填。每项含: prompt, description, image_count, image_size",
            },
            "strategy": {
                "type": "string",
                "enum": ["parallel", "sequential", "iterative"],
                "description": "执行策略，action=create时选填，默认parallel",
            },
        },
        "required": ["action"],
    }

    async def execute(self, action: str = "list", **kwargs) -> ToolResult:
        db: AsyncSession | None = kwargs.get("db")
        if not db:
            return ToolResult(content="计划工具需要数据库会话", meta={"error": "no_db_session"})

        if action == "list":
            return await self._list_templates(db)

        if action == "apply":
            template_id = kwargs.get("template_id", "")
            variables = kwargs.get("variables", {})
            if isinstance(variables, str):
                import json
                variables = json.loads(variables)
            if not template_id:
                return ToolResult(content="应用模板需要指定 template_id", meta={"error": "missing_template_id"})
            return await self._apply_template(db, template_id, variables)

        if action == "create":
            return await self._create_template(db, kwargs)

        if action == "generate":
            return self._generate_plan()

        return ToolResult(content=f"未知操作: {action}", meta={"error": "unknown_action"})

    async def _list_templates(self, db: AsyncSession) -> ToolResult:
        templates = await list_templates(db)
        if not templates:
            return ToolResult(
                content="目前没有可用的计划模板。可以使用 action=generate 从零开始创建计划。",
                meta={"templates": []},
            )
        items = []
        for t in templates:
            steps_count = len(t.steps) if t.steps else 0
            items.append({
                "id": t.id,
                "name": t.name,
                "description": t.description or "",
                "strategy": t.strategy,
                "steps_count": steps_count,
                "is_builtin": t.is_builtin,
                "variables": t.variables,
            })
        content_lines = ["可用模板列表：", ""]
        for item in items:
            builtin_tag = " [内置]" if item["is_builtin"] else ""
            content_lines.append(f"- {item['name']}{builtin_tag} (id={item['id']}, 策略={item['strategy']}, 步骤={item['steps_count']})")
        return ToolResult(content="\n".join(content_lines), meta={"templates": items})

    async def _apply_template(self, db: AsyncSession, template_id: str, variables: dict) -> ToolResult:
        template = await get_template(db, template_id)
        if not template:
            return ToolResult(content=f"未找到模板 {template_id}，请先用 action=list 查看可用模板", meta={"error": "template_not_found"})
        try:
            request = PlanTemplateApplyRequest(template_id=template_id, variables=variables)
            steps = await apply_template(db, template_id, request)
            content_lines = [f"应用模板「{template.name}」，共 {len(steps)} 个步骤："]
            for i, s in enumerate(steps, 1):
                content_lines.append(f"{i}. {s.get('description', s.get('prompt', '')[:80])}")
            meta = {
                "template_name": template.name,
                "steps": steps,
                "strategy": template.strategy,
            }
            if template.strategy == "style_anchor":
                meta["items"] = variables.get("items", [])
                meta["style"] = variables.get("style", "")
                meta["overall_theme"] = variables.get("overall_theme", "")
            return ToolResult(content="\n".join(content_lines), meta=meta)
        except Exception as e:
            return ToolResult(content=f"应用模板失败: {e}", meta={"error": str(e)})

    async def _create_template(self, db: AsyncSession, kwargs: dict) -> ToolResult:
        name = kwargs.get("name", "")
        if not name:
            return ToolResult(content="创建模板需要指定 name", meta={"error": "missing_name"})
        description = kwargs.get("description", "")
        strategy = kwargs.get("strategy", "parallel")
        raw_steps = kwargs.get("steps", [])

        steps = []
        for s in raw_steps:
            if isinstance(s, dict):
                steps.append(PlanStepSchema(
                    prompt=s.get("prompt", ""),
                    description=s.get("description", s.get("prompt", "")[:100]),
                    image_count=s.get("image_count", 1),
                    image_size=s.get("image_size", "1024x1024"),
                ))

        try:
            data = PlanTemplateCreate(
                name=name,
                description=description,
                strategy=strategy,
                steps=steps,
                variables=kwargs.get("variables", []),
            )
            template = await create_template(db, data)
            return ToolResult(
                content=f"已创建模板「{name}」({template.id})",
                meta={"template_id": template.id, "name": name},
            )
        except Exception as e:
            return ToolResult(content=f"创建模板失败: {e}", meta={"error": str(e)})

    def _generate_plan(self) -> ToolResult:
        return ToolResult(
            content=(
                "现在请根据用户需求，用以下格式生成一个生图计划：\n\n"
                "计划名称：<简短描述>\n"
                "执行策略：parallel（并发生成）或 sequential（顺序执行）或 iterative（迭代优化）\n\n"
                "步骤1：\n  - 提示词：<英文生图提示词>\n  - 说明：<这一步要生成什么>\n"
                "步骤2：\n  - 提示词：<英文生图提示词>\n  - 说明：<这一步要生成什么>\n\n"
                "输出计划后，按步骤调用 generate_image 工具逐一生成。如果搜索结果提供了有价值的参考，"
                "在调用 generate_image 时传入合适的 reference_urls。"
            ),
            meta={"trigger_generate": True},
        )
