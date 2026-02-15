# Frontend Progress (Swim Lane A)

## Context
- Plan reviewed in `PLAN.md`.
- Auth gate added via `/auth/me` to require GitHub sign-in.
- Integrity signals are captured in the UI and sent in answer payloads.
- `backend.md` and `llm.md` reviewed for alignment.

## Decisions
- Use Vite + React + TypeScript (already scaffolded).
- Default to mock API responses only when `VITE_USE_MOCKS=true`.
- Render all questions on one page for v1.
- Autosave uses `localStorage` keyed by repo URL to persist in-progress answers.
- Repo verification is a preflight step before submission via `/repos/verify`.
- Frontend points directly to `http://localhost:8000` with backend CORS enabled.

## Task 1: Repo Submission UI + Validation
**Status:** Completed

**What’s in place**
- Repo URL form with inline validation and error state.
- Preflight repo verification before question generation.
- Synchronous submit flow wired to `createSubmission` (mock or real API).
- Success state that confirms question generation and allows reset.
- No loading spinner during question generation (removed per request).

**Code locations**
- UI: `frontend/src/App.tsx`
- API client + types: `frontend/src/api.ts`, `frontend/src/types.ts`
- Config toggles: `frontend/src/config.ts`
- Styling: `frontend/src/styles.css`

## Next Tasks
All Swim Lane A tasks are complete.

## Task 2: Question Flow + Answer Submission
**Status:** Completed

**What’s in place**
- Questions render after submission, with file context and code excerpt.
- Answers captured per question and submitted in a single batch request.
- Timing/focus/paste telemetry is sent with answer submissions.
- Submission is blocked until all answers are non-empty; empty fields are highlighted.
- UI transitions to completion immediately after submit; network request continues in background.
- Success state after answer submission with option to start over.

**Code locations**
- Question flow UI + answer submission: `frontend/src/App.tsx`
- Answer API wiring: `frontend/src/api.ts`
- Answer types: `frontend/src/types.ts`
- Additional styles: `frontend/src/styles.css`

## Task 3: CSV Export Trigger
**Status:** Completed

**What’s in place**
- Instructor panel with CSV download link.
- Export URL derived from API base config.

**Code locations**
- UI: `frontend/src/App.tsx`
- API helper: `frontend/src/api.ts`
- Styling: `frontend/src/styles.css`

## Task 4: Auth UI + Integrity Controls
**Status:** Completed

**What’s in place**
- Auth gate with sign-in explainer and GitHub OAuth link.
- Signed-in header with GitHub login + sign-out.
- Paste blocking with inline warning per question.
- Focus-loss warnings via visibility/blur listeners.
- Timing capture per question (in-memory + autosave).
- Local autosave of answers/timing in `localStorage` keyed by repo URL.
- Integrity telemetry included in answer submissions (paste attempts, focus loss count, time spent).

**Code locations**
- Auth gate + integrity UI: `frontend/src/App.tsx`
- Warning styles and layout updates: `frontend/src/styles.css`
