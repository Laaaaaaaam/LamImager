from typing import Annotated

from langgraph.graph.message import add_messages
from typing import TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    messages: Annotated[list, add_messages]
    provider_id: str
    tools: list[str]
    total_tokens_in: int
    total_tokens_out: int
    cost: float
    rounds: int
    tools_used: list[str]
    intent: dict | None
    skill_hints: dict | None
    planning_context: dict | None
    execution_plan: dict | None
    optimized_prompts: list[str]
    artifacts: list[dict]
    critic_results: list[dict]
    retry_count: int
    status: str
    skill_ids: list[str]
    context_images: list[str]
    reference_images: list[str]
    reference_labels: list[dict]
    context_reference_urls: list[str]
    search_context: str
    image_provider_id: str
    llm_provider_id: str
    image_size: str
    negative_prompt: str
    image_count: int
    prompt: str
    token_budget: dict | None
    decision_result: str
    retry_step_index: int
    needs_search: bool
