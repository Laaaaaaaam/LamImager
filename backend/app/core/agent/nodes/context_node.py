import logging

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.agent.state import AgentState
from app.core.agent.llm_call_logger import LLMCallRecord, log_and_bill, LLMTimer
from app.services.planning_context import PlanningContextManager

logger = logging.getLogger(__name__)


async def context_enrichment_node(state: AgentState, config: RunnableConfig) -> dict:
    conf = config.get("configurable", {})
    db = conf.get("db")

    from app.core.events import LamEvent
    from app.services.task_manager import TaskManager, TaskStatus
    _tm = conf.get("task_manager") or TaskManager()

    prompt = state.get("prompt", "")
    negative_prompt = state.get("negative_prompt", "")
    session_id = state.get("session_id", "")
    image_count = state.get("image_count", 1)
    image_size = state.get("image_size", "1024x1024")
    skill_hints = state.get("skill_hints")
    search_context = state.get("search_context", "")
    needs_search = state.get("needs_search", False)
    reference_images = list(state.get("reference_images", []))
    context_images = list(state.get("context_images", []))
    context_reference_urls = list(state.get("context_reference_urls", []))
    reference_labels = list(state.get("reference_labels", []))

    if needs_search and not search_context and db:
        search_context = await _do_search_enhancement(db, session_id, prompt, _tm)

    llm_provider_id = state.get("llm_provider_id", "")
    llm_api_key = ""
    llm_base_url = ""
    llm_model_id = ""
    if db and llm_provider_id:
        from app.models.api_provider import ApiProvider
        from app.services.generate_service import resolve_provider_vendor
        result = await db.execute(select(ApiProvider).where(ApiProvider.id == llm_provider_id))
        provider = result.scalar_one_or_none()
        if provider:
            try:
                llm_base_url, llm_api_key = await resolve_provider_vendor(db, provider)
                llm_model_id = provider.model_id
            except Exception:
                pass

    mgr = PlanningContextManager(
        session_id=session_id,
        prompt=prompt,
        negative_prompt=negative_prompt,
        image_count=image_count,
        image_size=image_size,
        reference_images=reference_images,
        context_images=context_images,
        context_reference_urls=context_reference_urls,
        reference_labels=reference_labels,
        search_context=search_context,
        skill_hints=skill_hints,
    )

    deduped = mgr.deduplicate_images()

    token_budget = mgr.budget_tokens()

    if token_budget.get("total", 0) > 6000:
        overflow = token_budget["total"] - 6000
        if mgr.search_context and overflow > 0:
            search_est = token_budget.get("search", 0)
            if search_est > 0:
                reduction = min(search_est, overflow)
                truncation_ratio = max(0, (search_est - reduction)) / max(search_est, 1)
                if truncation_ratio < 1.0:
                    max_chars = int(len(mgr.search_context) * truncation_ratio)
                    mgr.search_context = mgr.search_context[:max_chars] + "..."
                    overflow -= reduction
                    logger.info(f"context_enrichment_node: truncated search_context by {reduction} tokens")

        if overflow > 0:
            auto_ctx_urls = deduped.get("context_reference_urls", [])
            if auto_ctx_urls:
                removals = min(len(auto_ctx_urls), (overflow // 85) + 1)
                deduped["context_reference_urls"] = auto_ctx_urls[removals:]
                mgr.context_reference_urls = auto_ctx_urls[removals:]
                overflow -= removals * 85
                logger.info(f"context_enrichment_node: removed {removals} auto_context URLs")

        token_budget = mgr.budget_tokens()

    image_urls = deduped.get("context_images", []) + deduped.get("context_reference_urls", [])
    if image_urls and llm_api_key and db:
        with LLMTimer() as timer:
            await mgr.cache_image_descriptions(
                db=db,
                image_urls=image_urls,
                llm_api_key=llm_api_key,
                llm_base_url=llm_base_url,
                llm_model_id=llm_model_id,
                task_manager=_tm,
                session_id=session_id,
            )

            if db and llm_provider_id:
                desc_count = len([u for u in image_urls if u in mgr._image_descriptions])
                if desc_count > 0:
                    await log_and_bill(db, LLMCallRecord(
                        node="context_vision",
                        model_id=llm_model_id,
                        provider_id=llm_provider_id,
                        session_id=session_id,
                        tokens_in=desc_count * 85,
                        tokens_out=desc_count * 50,
                        latency_ms=timer.ms,
                        billing_type="vision",
                        system_prompt="Describe this image in 2-3 concise English sentences. Focus on style, colors, composition, and subject.",
                        user_content=str(image_urls[:4]),
                        response_text=str(list(mgr._image_descriptions.values())),
                        extra={"described_images": desc_count},
                    ))

    mgr_dict = mgr.to_dict()

    if db:
        from app.services.settings_service import get_setting
        critic_mode_val = await get_setting(db, "critic_mode")
        critic_mode = (critic_mode_val or {}).get("value", "off") if isinstance(critic_mode_val, dict) else "off"
        critic_max_retry_val = await get_setting(db, "critic_max_retry")
        critic_max_retry = (critic_max_retry_val or {}).get("value", 2) if isinstance(critic_max_retry_val, dict) else 2
        mgr_dict["critic_mode"] = critic_mode
        mgr_dict["critic_max_retry"] = int(critic_max_retry)

    await _tm.publish(LamEvent(
        event_type="task_progress",
        correlation_id=f"agent-{session_id}",
        payload={
            "type": "agent_node_progress",
            "session_id": session_id,
            "node": "context",
            "status": "done",
            "message": "整理上下文",
            "content": f"参考图 {len(deduped.get('context_images', [])) + len(deduped.get('context_reference_urls', []))} 张, token 预算 {token_budget.get('total', 0)}",
            "detail": {
                "images": len(deduped.get("context_images", [])) + len(deduped.get("context_reference_urls", [])),
                "budget": token_budget.get("total", 0),
            },
        },
    ))

    logger.info(
        f"context_enrichment_node: "
        f"refs={len(deduped.get('reference_images', []))} "
        f"ctx_imgs={len(deduped.get('context_images', []))} "
        f"urls={len(deduped.get('context_reference_urls', []))} "
        f"budget={token_budget.get('total', 0)} "
        f"cached={len(mgr_dict.get('image_descriptions', {}))}"
    )

    return {
        "reference_images": deduped["reference_images"],
        "context_images": deduped["context_images"],
        "context_reference_urls": deduped["context_reference_urls"],
        "search_context": mgr.search_context,
        "token_budget": token_budget,
        "planning_context": mgr_dict,
    }


async def _do_search_enhancement(
    db,
    session_id: str,
    prompt: str,
    task_manager,
) -> str:
    from app.models.api_provider import ApiProvider, ProviderType
    from app.services.billing_service import record_billing, calc_cost
    from app.services.session_manager import add_system_message
    from app.services.api_manager import resolve_provider_vendor
    from app.services.settings_service import get_setting
    from app.tools.web_search import WebSearchTool
    from app.tools.image_search import ImageSearchTool

    logger.info(f"_do_search_enhancement: start, session_id={session_id}, prompt={prompt[:60]}...")

    search_provider_result = await db.execute(
        select(ApiProvider).where(
            ApiProvider.provider_type == ProviderType.web_search,
            ApiProvider.is_active == True,
        )
    )
    search_provider = search_provider_result.scalars().first()
    if not search_provider:
        logger.info("_do_search_enhancement: no web_search provider configured, skipping")
        return ""

    try:
        _, api_key = await resolve_provider_vendor(db, search_provider)
    except Exception as e:
        logger.warning(f"_do_search_enhancement: search API key decryption failed: {e}")
        return ""

    retry_count_val = await get_setting(db, "search_retry_count")
    retry_count = retry_count_val.get("value", 3) if retry_count_val else 3

    logger.info(f"_do_search_enhancement: search provider found, retry_count={retry_count}")

    task_manager.update_task(session_id, TaskStatus.GENERATING,
        message="搜索参考资料中...")

    search_context_parts = []

    logger.info(f"_do_search_enhancement: executing web search")
    web_tool = WebSearchTool()
    web_result = await web_tool.execute(query=prompt, max_results=5, api_key=api_key, retry_count=retry_count)
    if web_result.content and not web_result.meta.get("error"):
        search_context_parts.append(f"[网页搜索结果]\n{web_result.content}")
        logger.info(f"_do_search_enhancement: web search success, result length={len(web_result.content)}")
        await record_billing(db, session_id=session_id, provider_id=search_provider.id,
            billing_type=search_provider.billing_type.value,
            cost=calc_cost(search_provider, call_count=1),
            currency=search_provider.currency,
            detail={"type": "tool", "tool": "web_search", "agent": True})
        await add_system_message(db, session_id,
            "搜索参考: 找到相关网页资料",
            message_type="image",
            metadata={"search_type": "web", "sources": web_result.meta.get("sources", [])})
    else:
        logger.info(f"_do_search_enhancement: web search failed or empty")

    logger.info(f"_do_search_enhancement: executing image search")
    image_tool = ImageSearchTool()
    img_result = await image_tool.execute(query=prompt, max_results=5, api_key=api_key, retry_count=retry_count)
    if img_result.content and not img_result.meta.get("error"):
        search_context_parts.append(f"[图片搜索结果]\n{img_result.content}")
        image_urls = [s.get("image_url", "") for s in img_result.meta.get("sources", []) if s.get("image_url")]
        await record_billing(db, session_id=session_id, provider_id=search_provider.id,
            billing_type=search_provider.billing_type.value,
            cost=calc_cost(search_provider, call_count=1),
            currency=search_provider.currency,
            detail={"type": "tool", "tool": "image_search", "agent": True})
        if image_urls:
            logger.info(f"_do_search_enhancement: image search success, found {len(image_urls)} images")
            await add_system_message(db, session_id,
                f"搜索参考: 找到 {len(image_urls)} 张参考图",
                message_type="image",
                metadata={"search_type": "image", "image_urls": image_urls[:4]})
        else:
            logger.info(f"_do_search_enhancement: image search success but no image URLs")
    else:
        logger.info(f"_do_search_enhancement: image search failed or empty")

    result = "\n\n".join(search_context_parts)
    logger.info(f"_do_search_enhancement: completed, context length={len(result)}")
    return result
