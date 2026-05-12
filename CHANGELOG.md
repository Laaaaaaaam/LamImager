# Changelog

## [0.3.2] - 2026-05-12

### Fixed
- `_build_agent_context()` finally injects real multimodal `image_url` content parts instead of text-only `[上下文包含 X 张图片]` description
- `_build_agent_context()` was dead code — now called by `agent_service.py:run_agent_loop()` injecting session images into sidebar assistant context
- Frontend `contextMessages`: agent messages (`message_type: "agent"`) with `metadata.images` now extracted into `image_urls` (previously filtered by `message_type === "image"` and metadata key `"image_urls"`, missing all agent-generated images)
- Frontend shared context mode: context image URLs now injected as proper multimodal `image_url` content parts (previously flattened to text-only)
- `LamImager.spec`: added explicit `python314.dll` binary entry to prevent PyInstaller from bundling the wrong `python39.dll` from system PATH

## [0.3.1-beta] - 2026-05-11

### Added
- `api_vendors` table: vendors store name, base_url, and encrypted API key (one key per vendor)
- `vendor_id` FK on `api_providers`: models link to a vendor instead of duplicating credentials
- `/api/vendors` CRUD endpoints + `/api/vendors/{id}/models` sub-resource + `/api/vendors/{id}/test`
- `resolve_provider_vendor()` helper: vendor-first resolution with provider fallback

### Fixed
- `vendor_to_response` / `provider_to_response`: MissingGreenlet errors (added `selectinload` + pre-computed `model_count`)
- `init_db()`: ALTER TABLE plan_templates now guards against missing table
- `init_db()`: adds `api_vendors` table and `vendor_id` column if missing on existing DB
- `resolve_provider_vendor`: falls back to provider's own key when vendor decryption fails (handles migration grouping edge case)

### Changed
- **Key derivation**: switched from machine fingerprint (MAC + hostname) to file-based seed (`<DATA_DIR>/.encryption_seed`) for portability
- Frontend `ApiManage.vue`: redesigned with vendor table + expandable models sub-table + dual drawers
- Frontend `Settings.vue`: provider dropdowns show `vendor_name / model_id` format
- Version bumped to 0.3.1-beta

## [0.2.1] - 2026-05-11

### Added
- `plan_executor.py` with `execute_parallel` (Semaphore-based concurrent) and `execute_iterative` (sequential with image pass-through) backend executors
- PlanTool `get_detail` action — LLM can inspect full template steps before applying
- Template validation: strategy whitelist, min 1 step, prompt required on create/update; required variables enforced on apply (422 errors)
- User-selected `agent_plan_strategy` now consumed by backend — overrides intent strategy when set
- Frontend: type-aware template variable inputs (string/text, select/dropdown, number), required field red star
- Frontend: `radiate` strategy exposed in Plan tab radio buttons and template editor

### Fixed
- Builtin 套图生成 template: `{style}` → `{{style}}` variable syntax aligned with regex
- `_extract_items_from_text`: removed placeholder fallback generating bare "item N" prompts
- `PlanTool._apply_template`: removed dead `template_id` kwarg to `PlanTemplateApplyRequest`
- Removed debug hardcoded path writes `E:/LamImager/radiate_debug.log`

### Changed
- `PlanTemplate` model: added `builtin_version` column with auto-update on seed
- `PlanTemplateResponse`: now includes `builtin_version` field
- `PlanStepSchema`: removed dead `condition` field; `PlanStepConditionSchema` deleted; `reference_step_indices` deprecated
- `TemplateVariableSchema.default`: type changed from `str` to `Any` (supports array defaults like `[]`)
- `GenerateRequest.plan_strategy`: marked deprecated (unused by backend)
- AGENTS.md: rewritten Agent System section to reflect intent-based routing

## [0.2.0] - 2026-05-11

### Added
- Agent mode now fully supports uploaded reference_images (base64) and reference_labels — all 4 executors (single, parallel, iterative, radiate) merged user uploads with context URL references
- Multimodal LLM reasoning in planning phase: `_generate_radiate_params`, `_generate_iterative_steps`, `_generate_item_prompts` inject context images (max 2) for visual style guidance
- Hybrid intent parsing: regex confidence scoring (0.3-1.0) + LLM fallback classifier when confidence < 0.8, with `_pick_best_intent()` decision policy
- Upload buttons (image + document) now visible in agent mode UI
- `generate_image` tool supports `reference_images` (base64) and `reference_labels` params

### Fixed
- `handle_agent_generate` previously ignored `data.reference_images` entirely — now merges user-uploaded base64 images with context-derived URL references
- `_execute_single` previously passed raw URLs to `generate_images_core` without base64 conversion
- `execute_iterative` had no initial reference image injection — now uses uploaded/reference images on step 1
- `_execute_radiate` had no reference image support — now includes user images in item expansion chat_edit and fallback path
- `_build_agent_context` now extracts `image_urls` from message metadata for multimodal context

## [0.1.0] - 2026-05-10
