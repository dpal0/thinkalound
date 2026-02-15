# Backend Progress (Swim Lane B)

## Scope Notes
- Auth is deferred for now; repo URLs are treated as public personal repos.
- All backend work lives under `backend/`.

## Task List (Sequential)
1. **Repo verification (public personal repos)** — validate GitHub URL and confirm repo exists and is owned by a user account. (done)
2. **Repo ingestion + snippet extraction** — download archive, filter files, and extract code snippets in-memory. (done)
3. **DB models + initialization** — SQLAlchemy models for all tables and DB initialization. (done)
4. **REST endpoints** — submissions, questions, answers, grades, CSV export. (done)
5. **LLM module interface** — Lane C contract integration points for prompt building and response validation. (done)

## Decisions
- Use GitHub REST API `repos/{owner}/{repo}` for existence + `owner.type == "User"` to enforce personal repos.
- Store magic numbers in `backend/config/config.yaml` and prompt templates in `backend/config/prompts.yaml`.
- Use SQLAlchemy 2.0 with psycopg for PostgreSQL connectivity.
- Route LLM prompt building and schema validation through `backend/llm/module.py`, with HTTP calls and fallbacks in `backend/llm/interface.py`.
- Require `DATABASE_URL` to be set at startup (PostgreSQL).
- Backend entrypoint is `app.main` (run with `uv run python -m app.main`).
- OAuth secrets (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_REDIRECT_URI`, `JWT_SECRET`, `TOKEN_ENCRYPTION_KEY`) come from env vars.
- If `TOKEN_ENCRYPTION_KEY` is unset, tokens are stored unencrypted (dev-only behavior).
- If `JWT_SECRET` is unset, JWTs use an empty secret (dev-only behavior).

## Progress Log
- 2025-01-17: Initialized backend lane; created baseline Flask app and uv project (moved under `backend/`).
- 2025-01-17: Task 1 complete — repo verification utilities in `backend/services/github.py`, config loader in `backend/config/__init__.py`, and tuning values in `backend/config/config.yaml`.
- 2025-01-17: Task 2 complete — repo ingestion and snippet extraction in `backend/services/ingestion.py`, `backend/services/repo_ingest.py`, and `backend/services/snippets.py`.
- 2025-01-17: Task 3 complete — SQLAlchemy base and models in `backend/db/__init__.py` and `backend/db/models.py`.
- 2025-01-17: Task 4 complete — REST endpoints in `backend/api/routes.py` and Flask wiring in `backend/app/main.py`.
- 2025-01-17: Task 5 complete — LLM prompt/schema wiring in `backend/llm/module.py` and HTTP-backed fallback flow in `backend/llm/interface.py`.
- 2025-01-17: Hardened `/answers` validation and expanded CSV export columns in `backend/api/routes.py`.
- 2025-01-17: `POST /submissions` now accepts optional `commit_sha` override and errors when no snippets are found.
- 2025-01-17: Reorganized backend into packages (`app/`, `api/`, `config/`, `db/`, `services/`, `llm/`).
- 2025-01-17: Verified tests after reorg (`uv run --extra dev pytest -q`).
- 2025-01-17: Updated `/answers` to accept a batch payload (`answers[]`) in `backend/api/routes.py`.
- 2025-01-17: Re-ran backend pytest suite after batch answers change (9 passed).
- 2025-01-17: Switched snippet extraction to AST/brace-based blocks and added LLM snippet selection in `backend/services/snippets.py` and `backend/llm/interface.py`.
- 2025-01-17: Updated snippet selection config and tests for new SnippetConfig fields; tests pass.
- 2025-01-17: Added cleanup of unanswered questions before new submissions in `backend/db/storage.py` and `backend/api/routes.py`.
- 2025-01-17: Re-ran backend pytest suite after unanswered cleanup change (9 passed).
- 2025-01-17: Updated LLM request payload to use `max_completion_tokens` for OpenAI models in `backend/llm/interface.py`.
- 2025-01-17: Added async grading via background task queue (`backend/app/tasks.py`, `backend/services/grading.py`) and made `/answers` return 202 immediately.
- 2025-01-17: Queued grading after DB commit to avoid race conditions; tests pass.
- 2025-01-17: Added batch grading logs with submission ID in `backend/services/grading.py`.
- 2025-01-17: Implemented GitHub OAuth flow, JWT cookies, auth middleware, and user-bound access controls.
- 2025-01-17: Added auth crypto/JWT dependencies (pyjwt, cryptography) to backend env.
- 2025-01-17: Added `rationale` to CSV export output in `backend/api/routes.py`.
- 2025-01-17: Added `answer_text` to CSV export output in `backend/api/routes.py`.
- 2025-01-17: Updated grader prompt to require 2-3 sentence constructive feedback in `backend/config/prompts.yaml`.
