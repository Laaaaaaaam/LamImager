from __future__ import annotations

from app.tools.base import Tool, ToolResult


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_openai_schemas(self) -> list[dict]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def list_for_openai(self, tool_names: list[str] | None) -> list[dict] | None:
        if not tool_names:
            return None
        schemas = []
        for name in tool_names:
            tool = self._tools.get(name)
            if tool:
                schemas.append(tool.to_openai_schema())
        return schemas or None


registry = ToolRegistry()


def register_tool(tool: Tool) -> Tool:
    return registry.register(tool)


from app.tools.web_search import WebSearchTool
from app.tools.image_search import ImageSearchTool

registry.register(WebSearchTool())
registry.register(ImageSearchTool())
