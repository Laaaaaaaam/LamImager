import logging

from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import interrupt
from langchain_core.runnables import RunnableConfig

from app.core.agent.state import AgentState
from app.core.agent.graph_llm import agent_node
from app.core.agent.graph_tools import tools_node
from app.core.agent.nodes.skill_node import skill_node
from app.core.agent.nodes.skill_matcher_node import skill_matcher_node
from app.core.agent.nodes.context_node import context_enrichment_node
from app.core.agent.nodes.intent_node import intent_node

logger = logging.getLogger(__name__)

_memory_saver = InMemorySaver()


def _should_continue(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    if status == "has_tool_calls":
        return "tools"
    return END


def build_agent_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)

    graph.set_entry_point("agent")

    graph.add_conditional_edges("agent", _should_continue)

    graph.add_edge("tools", "agent")

    return graph.compile(checkpointer=_memory_saver)


async def executor_node(state: AgentState, config: RunnableConfig) -> dict:
    from app.schemas.execution import ExecutionPlan
    from app.schemas.planning import PlanningContext
    from app.services.executors.engine import ExecutionEngine
    from app.services.task_manager import TaskManager, TaskStatus
    from app.core.events import LamEvent

    conf = config.get("configurable", {})
    db = conf.get("db")
    session_id = state.get("session_id", "")
    task_manager = conf.get("task_manager") or TaskManager()

    plan_dict = state.get("execution_plan")
    if not plan_dict:
        return {"status": "error", "artifacts": []}

    plan = ExecutionPlan(**plan_dict) if isinstance(plan_dict, dict) else plan_dict

    planning_ctx = state.get("planning_context", {})
    context = PlanningContext(**planning_ctx) if isinstance(planning_ctx, dict) else PlanningContext()

    context.image_provider_id = state.get("image_provider_id", "") or None
    context.llm_provider_id = state.get("llm_provider_id", "") or None
    context.session_id = state.get("session_id", "")

    checkpoint_steps = [s for s in plan.steps if isinstance(s.checkpoint, dict) and s.checkpoint.get("enabled")]

    await task_manager.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{session_id}",
        payload={
            "type": "task_progress",
            "session_id": session_id,
            "task_type": state.get("intent", {}).get("task_type", "single"),
            "strategy": plan.strategy,
            "message": f"执行计划: {plan.strategy}, {len(plan.steps)} 步",
        },
    ))

    await task_manager.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{session_id}",
        payload={
            "type": "agent_node_progress",
            "session_id": session_id,
            "node": "executor",
            "status": "running",
            "message": f"执行计划: {plan.strategy}, {len(plan.steps)} 步",
            "detail": {"strategy": plan.strategy, "steps": len(plan.steps)},
        },
    ))

    engine = ExecutionEngine(plan, context)

    existing_artifacts = state.get("artifacts", [])
    if existing_artifacts:
        from app.services.executors.engine import Artifact, StepTrace
        for i, art_dict in enumerate(existing_artifacts):
            if i < len(plan.steps):
                fake_trace = StepTrace(
                    step_index=i,
                    status="completed",
                    started_at="",
                    completed_at="",
                )
                fake_trace.artifacts.append(Artifact(
                    type=art_dict.get("type", "image"),
                    url=art_dict.get("url", ""),
                    metadata=art_dict.get("metadata", {}),
                ))
                engine.completed.append(fake_trace)
        engine.current_index = len(engine.completed)

    all_artifacts: list[dict] = list(existing_artifacts)
    total_tokens_in = state.get("total_tokens_in", 0)
    total_tokens_out = state.get("total_tokens_out", 0)
    total_cost = state.get("cost", 0.0)
    checkpoint_indices = {s.index for s in checkpoint_steps}

    groups = engine.group_steps()

    for group in groups:
        if engine.is_done:
            break

        if task_manager.get_cancel_event(session_id).is_set():
            logger.info(f"executor_node: cancelled")
            return {
                "artifacts": all_artifacts,
                "total_tokens_in": total_tokens_in,
                "total_tokens_out": total_tokens_out,
                "cost": total_cost,
                "status": "cancelled",
            }

        if len(group) == 1:
            step_idx = group[0]
            await task_manager.publish(LamEvent(
                event_type="task_progress",
                correlation_id=f"agent-{session_id}",
                payload={
                    "type": "agent_node_progress",
                    "session_id": session_id,
                    "node": "executor",
                    "status": "running",
                    "message": f"步骤 {step_idx + 1}/{len(plan.steps)}",
                    "detail": {"step_index": step_idx, "step_total": len(plan.steps), "strategy": plan.strategy},
                },
            ))

            st = await engine.step(db, task_manager)

            for a in st.artifacts:
                all_artifacts.append({"type": a.type, "url": a.url, "metadata": a.metadata})

            total_tokens_in += st.tokens_in
            total_tokens_out += st.tokens_out
            total_cost += st.cost

            step_artifact_urls = [a.url for a in st.artifacts if a.type == "image"]
            await task_manager.publish(LamEvent(
                event_type="task_progress",
                correlation_id=f"agent-{session_id}",
                payload={
                    "type": "agent_node_progress",
                    "session_id": session_id,
                    "node": "executor",
                    "status": "step_done",
                    "message": f"步骤 {step_idx + 1}/{len(plan.steps)} 完成",
                    "detail": {
                        "step_index": step_idx,
                        "step_total": len(plan.steps),
                        "strategy": plan.strategy,
                        "step_prompt": plan.steps[step_idx].prompt[:200],
                        "step_description": plan.steps[step_idx].description,
                        "image_urls": step_artifact_urls,
                        "tokens_in": st.tokens_in,
                        "tokens_out": st.tokens_out,
                        "cost": st.cost,
                    },
                },
            ))

            step = plan.steps[step_idx]
            if step.checkpoint and isinstance(step.checkpoint, dict) and step.checkpoint.get("enabled"):
                step_artifacts = [{"type": a.type, "url": a.url, "metadata": a.metadata} for a in st.artifacts]

                await task_manager.publish(LamEvent(
                    event_type="checkpoint_required",
                    correlation_id=f"agent-{session_id}",
                    payload={
                        "type": "agent_checkpoint",
                        "session_id": session_id,
                        "message": step.checkpoint.get("message", ""),
                        "step": {"index": step.index, "description": step.description or step.prompt[:80]},
                        "step_index": step.index,
                        "step_role": getattr(step, "role", ""),
                        "artifacts": step_artifacts,
                    },
                ))

                action = interrupt({
                    "type": "checkpoint_required",
                    "session_id": session_id,
                    "step_index": step.index,
                    "step_role": getattr(step, "role", ""),
                    "message": step.checkpoint.get("message", ""),
                    "artifacts": step_artifacts,
                })

                logger.info(f"executor_node: checkpoint resolved for step {step.index}: action={action}")

                if action == "replan":
                    logger.info(f"executor_node: replan requested at step {step.index}")
                    return {
                        "artifacts": all_artifacts,
                        "total_tokens_in": total_tokens_in,
                        "total_tokens_out": total_tokens_out,
                        "cost": total_cost,
                        "status": "replan_needed",
                        "replan_step_index": step.index,
                    }

                if action == "retry_step":
                    logger.info(f"executor_node: retry_step at step {step.index}")
                    engine.rollback_step()
                    total_tokens_in -= st.tokens_in
                    total_tokens_out -= st.tokens_out
                    total_cost -= st.cost
                    for _ in st.artifacts:
                        if all_artifacts:
                            all_artifacts.pop()

                    retry_st = await engine.step(db, task_manager)
                    for a in retry_st.artifacts:
                        all_artifacts.append({"type": a.type, "url": a.url, "metadata": a.metadata})
                    total_tokens_in += retry_st.tokens_in
                    total_tokens_out += retry_st.tokens_out
                    total_cost += retry_st.cost
        else:
            await task_manager.publish(LamEvent(
                event_type="task_progress",
                correlation_id=f"agent-{session_id}",
                payload={
                    "type": "agent_node_progress",
                    "session_id": session_id,
                    "node": "executor",
                    "status": "running",
                    "message": f"并发执行 {len(group)} 个步骤",
                    "detail": {"strategy": plan.strategy, "parallel_steps": len(group)},
                },
            ))

            results = await engine.run_parallel_group(db, task_manager, group)
            for gi, st in enumerate(results):
                for a in st.artifacts:
                    all_artifacts.append({"type": a.type, "url": a.url, "metadata": a.metadata})
                total_tokens_in += st.tokens_in
                total_tokens_out += st.tokens_out
                total_cost += st.cost

                sidx = group[gi] if gi < len(group) else gi
                step_artifact_urls = [a.url for a in st.artifacts if a.type == "image"]
                await task_manager.publish(LamEvent(
                    event_type="task_progress",
                    correlation_id=f"agent-{session_id}",
                    payload={
                        "type": "agent_node_progress",
                        "session_id": session_id,
                        "node": "executor",
                        "status": "step_done",
                        "message": f"步骤 {sidx + 1}/{len(plan.steps)} 完成",
                        "detail": {
                            "step_index": sidx,
                            "step_total": len(plan.steps),
                            "strategy": plan.strategy,
                            "step_prompt": plan.steps[sidx].prompt[:200] if sidx < len(plan.steps) else "",
                            "step_description": plan.steps[sidx].description if sidx < len(plan.steps) else "",
                            "image_urls": step_artifact_urls,
                            "tokens_in": st.tokens_in,
                            "tokens_out": st.tokens_out,
                            "cost": st.cost,
                        },
                    },
                ))

    logger.info(
        f"executor_node: strategy={plan.strategy}, "
        f"artifacts={len(all_artifacts)}, status=executed"
    )

    await task_manager.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{session_id}",
        payload={
            "type": "agent_node_progress",
            "session_id": session_id,
            "node": "executor",
            "status": "done",
            "message": "执行完成",
            "detail": {"artifacts": len(all_artifacts)},
        },
    ))

    return {
        "artifacts": all_artifacts,
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
        "cost": total_cost,
        "status": "executed",
        "retry_step_index": -1,
    }


def _after_intent(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    return "skill_matcher"


def _after_skill_matcher(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    return "skill"


def _after_skill(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    return "context_enrichment"


def _after_context(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    return "planner"


def _after_planner(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    if not state.get("execution_plan"):
        return END
    return "prompt_builder"


def _after_prompt_builder(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    return "executor"


def _after_executor(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    if status == "replan_needed":
        return "planner"
    critic_mode = "off"
    planning_ctx = state.get("planning_context", {})
    if isinstance(planning_ctx, dict):
        critic_mode = planning_ctx.get("critic_mode", "off")
    if critic_mode == "off":
        return END
    return "critic"


def _after_critic(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    return "decision"


def _after_decision(state: AgentState) -> str:
    status = state.get("status", "")
    if status in ("cancelled", "error"):
        return END
    decision = state.get("decision_result", "")
    if decision == "retry_prompt":
        return "prompt_builder"
    if decision == "retry_step":
        return "executor"
    if decision == "replan":
        return "planner"
    return END


def build_agent_mode_graph() -> StateGraph:
    from app.core.agent.nodes.planner_node import planner_node
    from app.core.agent.nodes.prompt_builder_node import prompt_builder_node
    from app.core.agent.nodes.critic_node import critic_node
    from app.core.agent.nodes.decision_node import decision_node

    graph = StateGraph(AgentState)

    graph.add_node("intent", intent_node)
    graph.add_node("skill_matcher", skill_matcher_node)
    graph.add_node("skill", skill_node)
    graph.add_node("context_enrichment", context_enrichment_node)
    graph.add_node("planner", planner_node)
    graph.add_node("prompt_builder", prompt_builder_node)
    graph.add_node("executor", executor_node)
    graph.add_node("critic", critic_node)
    graph.add_node("decision", decision_node)

    graph.set_entry_point("intent")

    graph.add_conditional_edges("intent", _after_intent)
    graph.add_conditional_edges("skill_matcher", _after_skill_matcher)
    graph.add_conditional_edges("skill", _after_skill)
    graph.add_conditional_edges("context_enrichment", _after_context)
    graph.add_conditional_edges("planner", _after_planner)
    graph.add_conditional_edges("prompt_builder", _after_prompt_builder)
    graph.add_conditional_edges("executor", _after_executor)
    graph.add_conditional_edges("critic", _after_critic)
    graph.add_conditional_edges("decision", _after_decision)

    return graph.compile(checkpointer=_memory_saver)
