"""MentisQ — the AI tutor, a module inside the Core API (not a separate service).

- `llm_client` — the OpenRouter boundary (the only code that talks to the provider).
- `prompt` — the versioned guided-mode system prompt template + rendering.
- `settings` — typed accessors over the `Setting` table for the model name and caps.
- `service` — `MentisQService`: the guided exchange, cap checks, and persistence.

The HTTP layer is `app.routers.mentisq` (student exchange) and `app.routers.admin`
(the `SuperAdmin` settings endpoint).
"""
