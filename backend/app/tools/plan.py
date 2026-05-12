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
        "4. get_detail — 查看单个模板的完整内容（全部 steps 含 prompt/negative_prompt/checkpoint 等）\n"
        "对于 radiate/套图模板，apply 时 variables 必须包含 items(由你自主分析用户输入拆分的子项列表，每项含 prompt，禁止使用 item 1 等占位词)、style(视觉风格)、overall_theme(主题)。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "apply", "create", "get_detail"],
                "description": "操作类型：list=列出模板, apply=应用模板, create=保存模板, get_detail=查看模板详情",
            },
            "template_id": {
                "type": "string",
                "description": "模板ID，action=apply时必填",
            },
            "variables": {
                "type": "object",
                "description": "变量键值对，action=apply时用于填充模板。radiate/套图模板必须包含 items(子项列表)、style(视觉风格)、overall_theme(主题)。重要：items 必须由你自主分析用户输入拆分，每项含 prompt 字段描述具体内容。示例: 用户要求'4张橘猫表情包' → [{prompt:'happy orange cat, chibi'},{prompt:'sad orange cat, chibi'},{prompt:'angry orange cat, chibi'},{prompt:'surprised orange cat, chibi'}]。严禁使用 item 1/item 2 等占位词",
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
                "enum": ["parallel", "iterative", "radiate"],
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

        if action == "get_detail":
            template_id = kwargs.get("template_id", "")
            if not template_id:
                return ToolResult(content="查看详情需要指定 template_id", meta={"error": "missing_template_id"})
            return await self._get_detail(db, template_id)

        return ToolResult(content=f"未知操作: {action}", meta={"error": "unknown_action"})

    async def _list_templates(self, db: AsyncSession) -> ToolResult:
        templates = await list_templates(db)
        if not templates:
            return ToolResult(
                content="目前没有可用的计划模板。请先调用 plan(action=\"create\", strategy=\"<合适策略>\", name=\"<名称>\", steps=[{...}]) 新建模板，再调用 plan(action=\"apply\")。策略可选: parallel(并发)、iterative(顺序)、radiate(辐射)。",
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
            request = PlanTemplateApplyRequest(variables=variables)
            plan = await apply_template(db, template_id, request)
            steps = plan.to_steps_dict()
            content_lines = [f"应用模板「{template.name}」，共 {len(steps)} 个步骤："]
            for i, s in enumerate(steps, 1):
                content_lines.append(f"{i}. {s.get('description', s.get('prompt', '')[:80])}")
            meta = {
                "template_name": template.name,
                "steps": steps,
                "strategy": template.strategy,
                "plan": plan.model_dump(),
            }
            if template.strategy == "radiate":
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

    async def _get_detail(self, db: AsyncSession, template_id: str) -> ToolResult:
        template = await get_template(db, template_id)
        if not template:
            return ToolResult(content=f"未找到模板 {template_id}", meta={"error": "template_not_found"})
        steps_info = []
        for i, s in enumerate(template.steps or [], 1):
            step_info = {
                "step": i,
                "prompt": s.get("prompt", ""),
                "negative_prompt": s.get("negative_prompt", ""),
                "description": s.get("description", ""),
                "image_count": s.get("image_count", 1),
                "image_size": s.get("image_size", ""),
            }
            if s.get("checkpoint"):
                step_info["checkpoint"] = s["checkpoint"]
            if s.get("repeat"):
                step_info["repeat"] = s["repeat"]
            if s.get("role"):
                step_info["role"] = s["role"]
            if s.get("reference_step_indices"):
                step_info["reference_step_indices"] = s["reference_step_indices"]
            steps_info.append(step_info)
        content_lines = [f"模板「{template.name}」详情 (策略={template.strategy}, 步骤={len(steps_info)}):"]
        for si in steps_info:
            content_lines.append(f"  {si['step']}. {si['description'] or si['prompt'][:60]}")
            content_lines.append(f"     prompt: {si['prompt'][:120]}")
            if si.get("checkpoint"):
                content_lines.append(f"     checkpoint: {si['checkpoint']}")
        return ToolResult(
            content="\n".join(content_lines),
            meta={
                "template_id": template.id,
                "name": template.name,
                "description": template.description or "",
                "strategy": template.strategy,
                "is_builtin": template.is_builtin,
                "variables": template.variables,
                "steps": steps_info,
            },
        )
