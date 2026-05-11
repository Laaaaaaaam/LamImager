# Changelog

## [0.1.0] - 2026-05-10

### Added
- Initial release of LamImager
- Conversation-based image generation UI with session management
- AI agent mode with intelligent intent routing (single, multi-item, iterative, radiate)
- LLM-powered prompt optimization and planning with SSE streaming
- Function Calling tools: generate_image, web_search, image_search, plan
- Radiate strategy for consistent multi-item set generation (anchor grid + crop + expand)
- Plan template system with variable substitution and built-in templates
- API provider management with AES-256-GCM encrypted keys
- Billing tracking per API call with CSV export
- Dashboard with session/image/generation statistics
- Skills and Rules engine for reusable prompt workflows
- Reference image support with auto-context and refine mode
- SSRF-protected image proxy endpoint
- Image download to configured directory
- Real-time SSE event bus for cross-session task status
