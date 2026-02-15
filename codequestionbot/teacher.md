# Teacher Notes (Agent Oversight)

## Current Issues / Improvements
- `frontend/src/config.ts`: `VITE_USE_MOCKS` defaults to `"true"`, so production builds will silently use mocks unless the env var is set. Prefer defaulting to `false` or gating by `import.meta.env.MODE`.
- `frontend/src/App.tsx`: answers are submitted without sending timing/focus/paste telemetry to the backend. Decide whether to include these fields now or leave as a planned enhancement.

## Code Flow (Current)
- App boot: `backend/app/main.py` loads config, initializes DB schema, registers auth + API routes, and enforces JWT auth middleware.
- Auth: `/auth/github` -> OAuth redirect -> `/auth/github/callback` exchanges code, stores token, sets JWT cookie.
- Repo verify: `POST /repos/verify` -> `services.github.GitHubClient.verify_repo_url` -> returns owner/name if personal.
- Submission: `POST /submissions` -> `services.ingestion.ingest_repo` downloads GitHub zip, filters files (`backend/services/repo_ingest.py`), extracts snippets (`backend/services/snippets.py`) -> `llm.interface.generate_questions` (LLM with fallback) -> stores user/repo/submission/questions -> responds with question list.
- Questions fetch: `GET /submissions/{id}/questions` -> queries `questions` by submission_id -> responds with serialized questions.
- Answer grading: `POST /answers` -> validates submission + question -> creates answers -> enqueues background grading tasks -> responds 202 with queued status; grader writes grades asynchronously.
- Grades fetch: `GET /submissions/{id}/grades` -> joins grades + answers -> responds with scores/rationales.
- CSV export: `GET /exports/submissions.csv` -> joins answers/questions/submissions/repos/users/grades -> writes CSV rows with metadata and grade fields.
- Frontend flow: `frontend/src/App.tsx` -> submit repo -> render questions -> submit answers (single batch POST) -> show completion -> CSV download via `/exports/submissions.csv`.
