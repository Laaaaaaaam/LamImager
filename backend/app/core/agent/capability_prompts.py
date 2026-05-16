STRATEGY_EXECUTION_MECHANISM = """\
## Strategy Execution Mechanism

The system uses `reference_step_indices` to declare step-to-step image relationships. Each step can reference output images from specific previous steps as visual references for img2img editing.

1. **single** — One API call generating N images with the same prompt.
   - No `reference_step_indices` needed.
   - All images share identical prompt parameters.

2. **parallel** — Multiple independent API calls, each with a different prompt.
   - No `reference_step_indices` — all steps are independent.
   - Steps execute concurrently.

3. **iterative** — Sequential steps where each step references the previous step's output image.
   - Step N MUST have `reference_step_indices=[N-1]` — this is REQUIRED, not optional.
   - The system uses the referenced step's output as a reference image for img2img editing.
   - Without `reference_step_indices`, the step will NOT receive previous output images.

4. **radiate** — Generate a unified anchor grid, then crop and expand each cell into a standalone image.
   - Step 0 (anchor): no `reference_step_indices`.
   - Step 1..N (items): MUST have `reference_step_indices=[0]` — references the anchor step's output.
   - The system automatically crops the anchor grid into cells and uses each cell as a reference for the corresponding item step.
   - If grid crop fails, the system falls back to using the full anchor image as reference with style description.
"""

IMAGE_SYSTEM_CONSTRAINTS = """\
## System Constraints

- The system can only GENERATE images, not edit existing images in-place. "Refinement" means generating a new image using the old one as a visual reference.
- Cross-image character consistency is NOT guaranteed. The system uses style descriptions and reference images to approximate consistency, but identical characters across images are not reliable.
- img2img (chat_edit) provides STYLE GUIDANCE only — it does not preserve exact content from the reference image. The output will follow the reference's visual style but may differ in composition and details.
- Maximum concurrent image generation calls is limited by system settings (default 5).
- Supported image sizes depend on the model; common sizes are 1024x1024, 1024x1792, 1792x1024.
- The system has no built-in image editing tools (no inpainting, no selective modification). All operations produce new images.
"""

PLANNER_STRATEGY_GUIDE = """\
## Strategy-Specific Planning Rules

### Prompt quality principle
- Each step's prompt should be concise and focused — describe what to generate, not how to render it.
- Do NOT add generic quality keywords (highly detailed, professional, 8K, masterpiece) or unnecessary style/technique descriptors.
- Keep the user's original language. Only use English for specialized art/technical terms that lack good equivalents.
- If the user's request is already specific, preserve it as-is in the step prompt.

### single strategy
- Create exactly 1 step with the full prompt.
- Set image_count to the expected number of images.
- No reference_step_indices needed.
- No checkpoint needed.

### parallel strategy
- Create N steps, one per independent variation/view.
- Each step has its own distinct prompt targeting its specific variation.
- No reference_step_indices — all steps are independent.
- All steps can execute concurrently.
- For multi-view (front/side/back), each step should explicitly include the view angle in the prompt.

### iterative strategy
- Create 2-5 sequential steps where each step refines the previous.
- Step 0 is the base/rough version.
- Step N MUST have `reference_step_indices=[N-1]` to reference the previous step's output image. This is REQUIRED — without it, the step will not receive the previous image for refinement.
- Example: Step 0 has no reference_step_indices. Step 1 has reference_step_indices=[0]. Step 2 has reference_step_indices=[1].
- Each step should describe what to improve or add compared to the previous step.
- The first step should establish the basic composition; later steps add detail and refinement.
- Consider adding a checkpoint after the first step for user review.

### radiate strategy
- Create N steps, one per item in the set.
- Step 0 is the anchor grid generation. Steps 1..N are individual item expansions.
- Steps 1..N MUST have `reference_step_indices=[0]` to reference the anchor step's output. This is REQUIRED.
- The system automatically crops the anchor grid and uses each cell as a reference for the corresponding item step.
- Each step's prompt should describe ONE distinct item/pose/expression.
- Include a `plan_meta` object in your output with:
  - "items": array of {prompt, label} objects for each item
  - "style": visual style description (English)
  - "overall_theme": theme description (English)
- Do NOT create a composite/grid image prompt — the system handles grid generation internally.
"""

IMAGE_PROVIDER_CAPABILITIES = """\
## Image Provider Capabilities

Current model: {model_id}
Supported sizes: {supported_sizes}

When planning, ensure:
- Image sizes match the model's supported sizes.
- If the model doesn't support img2img, iterative strategy steps after step 0 will use text-only prompts with style descriptions from the previous step.
- Complex prompts work better with models that have strong instruction-following capabilities.
"""

PROMPT_BUILDER_GUIDE = """\
## Prompt Optimization Guide

Core principle: optimize for appropriateness, not length. A well-placed detail beats a wall of keywords.

1. **Respect original intent**: If the prompt is already specific enough, keep it as-is. Only expand vague parts.
   - Good: "橘猫在窗台上晒太阳" → keep as-is (already vivid and specific)
   - Needs help: "一只猫" → "一只橘猫蜷在窗台上，午后阳光洒在毛上"

2. **Style keywords**: Add art style/medium/technique ONLY when the user's intent implies a specific style, or when a skill bias requests it. Do not add style keywords to simple, everyday prompts.
   - Unnecessary: "一只猫, digital illustration, cel-shaded" (user just wanted a cat)
   - Appropriate: "赛博朋克风格的城市, neon-lit cyberpunk cityscape, digital painting" (style is the intent)

3. **Composition**: Describe camera angle/framing ONLY when composition matters to the intent. Skip for simple subjects.
   - Skip for: "一朵红花" (the flower is the point, not the angle)
   - Add for: "广阔的草原" → "广阔的草原，低角度远景，天际线在画面上方三分之一处"

4. **Lighting**: Add lighting details ONLY when lighting is part of the mood or intent. Do not add lighting to every prompt.
   - Skip for: "白天街景" (daytime is already clear)
   - Add for: "神秘的森林" → "神秘的森林，光线透过树冠形成丁达尔效应"

5. **Technical quality**: Do NOT add generic quality modifiers (highly detailed, sharp focus, professional quality, 8K, masterpiece). These are noise that dilute meaningful tokens. Trust the model's default quality.

6. **Negative prompts**: If the step has a negative_prompt, respect it — do not contradict it.

7. **Reference images**: If context image descriptions are provided, match their visual style and color palette.

8. **Skill bias**: Apply skill bias parameters (detail_level, style, quality) as guidance, not as literal text to append. Interpret them in context.

9. **Language**: Keep the prompt in the user's original language. Only use English for specialized art/technical terms that lack good equivalents (e.g., chiaroscuro, bokeh, cel-shaded, isometric). Do not translate entire prompts to English.
"""

CRITIC_EVALUATION_DIMENSIONS = """\
## Evaluation Dimensions

Score each image on these 6 dimensions:

1. **style** — Art style consistency and appropriateness (e.g. photorealistic, anime, oil painting)
2. **color_temperature** — Color palette warmth/coolness and harmony (e.g. warm, cool, neutral)
3. **composition** — Layout, framing, and visual balance (e.g. centered, rule-of-thirds, dynamic)
4. **lighting** — Light source, direction, and quality (e.g. natural, studio, dramatic)
5. **detail_level** — Level of visual detail and texture (e.g. high, medium, low)
6. **mood** — Emotional atmosphere and tone (e.g. calm, energetic, mysterious)

When listing issues, be specific and actionable:
- Instead of "bad composition", say "subject is too close to the edge, needs more negative space on the left"
- Instead of "wrong style", say "style is watercolor but request specified photorealistic"
- Instead of "quality issues", say "visible artifacts in the lower-right corner, blurry edges around the main subject"
"""


def build_planner_system_prompt(
    task_type: str,
    strategy_whitelist: list[str],
    image_size: str,
    skill_constraints: str,
    model_id: str = "",
    supported_sizes: str = "",
) -> str:
    parts = [
        "You are an image generation planner. Given the user's request, task type, and constraints, "
        "create an execution plan as a JSON object.\n\n",
        STRATEGY_EXECUTION_MECHANISM,
        "\n",
        IMAGE_SYSTEM_CONSTRAINTS,
        "\n",
        PLANNER_STRATEGY_GUIDE,
        "\n",
        "## Plan Output Format\n\n",
        'The plan must follow these rules:\n',
        f'- "strategy" must be one of: {strategy_whitelist}\n',
        '- "steps" is an array of step objects, each with:\n',
        '  - "prompt" (string, image generation prompt for this step, keep the user\'s original language; only use English for specialized art/technical terms that lack good equivalents)\n',
        '  - "description" (string, brief Chinese description)\n',
        '  - "image_count" (integer, default 1)\n',
        f'  - "image_size" (string, default "{image_size}")\n',
        '  - "negative_prompt" (string, optional)\n',
        '  - "reference_step_indices" (array of integers, optional, indices of previous steps whose images to reference)\n',
        '  - "checkpoint" (object with "enabled": true/false, optional)\n\n',
        "## When to add checkpoint\n",
        "- **iterative strategy**: ALWAYS add checkpoint with enabled=true on step 0\n",
        "  so user can review the rough draft before refinement continues.\n",
        "  Example: {\"enabled\": true, \"message\": \"确认草图后继续精修\"}\n",
        "- **radiate strategy**: add checkpoint on step 0 (anchor grid) before\n",
        "  expanding to individual items. Optional, skip if confidence is high.\n",
        "- **parallel/single strategy**: no checkpoint needed.\n\n",
        "For radiate strategy, also include:\n",
        '  - "plan_meta" object with "items", "style", "overall_theme" fields\n\n',
        "Constraints from skill:\n",
        f"{skill_constraints}\n\n",
        "If reference images are provided, use their visual style to guide the plan.\n",
        "If context image descriptions are provided, use them to understand the visual context.\n",
        "If search context is provided, use it as supplementary design reference but do not override the user's original intent.\n",
        "Output ONLY the JSON object, no markdown, no explanation.",
    ]

    if model_id:
        parts.append(f"\n\n{IMAGE_PROVIDER_CAPABILITIES.format(model_id=model_id, supported_sizes=supported_sizes or image_size)}")

    return "".join(parts)
