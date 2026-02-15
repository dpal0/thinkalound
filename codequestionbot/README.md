# CodeQuestionBot

CodeQuestionBot is a GitHub-authenticated auto-grader that turns a student’s repository into a set of code-specific questions and grades the responses with an LLM. It emphasizes integrity with lightweight anti-cheating signals (paste blocking, focus loss, timing) captured during the submission flow. 

Grading is automated, consistent, and stored alongside the student’s answers so instructors can review context quickly. Configuration is centralized in YAML so you can tune models, limits, prompts, and instructor access without code changes. 

The app is designed for small-to-medium course projects where you need rapid, structured feedback without manual grading overhead.

<p align="center">
<img width="1292" height="969" alt="Xnapper-2026-01-18-12 53 38" src="https://github.com/user-attachments/assets/2214cc9e-1312-4039-a83e-97c059bbc77a" />
</p>

Here is a video showing the basic functionality of entering a github url, generating questions, and exporting grades to instructors: https://www.loom.com/share/5ad3fe54551f4975855932fa81c369ae

## Architecture Overview

**Code organization**
- `frontend/`: React + TypeScript UI for sign-in, repo submission, question answering, and CSV export.
- `backend/`: Flask API with modular packages:
  - `app/` (startup + middleware), `api/` (routes), `auth/` (OAuth/JWT), `config/` (YAML settings + prompts),
  - `db/` (models + persistence), `services/` (repo ingestion, snippet extraction, grading), `llm/` (LLM prompt/response handling).

**Auth flow**
- Users sign in with GitHub OAuth; the backend stores an encrypted GitHub token and issues a JWT cookie.
- All non-auth endpoints require a valid JWT; instructors are determined by username in `config/config.yaml`.
- Repo access is verified with the user’s GitHub token and must be a personal repo owned by the authenticated user.

**Questioning + grading**
- The backend downloads a repo snapshot (default-branch HEAD), extracts candidate code blocks, and uses an LLM to select the most relevant snippets.
- It generates a fixed set of questions tied to stored excerpts; student answers are submitted in one batch.
- Grading runs asynchronously in a background task and writes scores plus 2–3 sentence constructive feedback (`rationale`) to the database.

**Instructor visibility**
- CSV export includes repo metadata, question context, student answers, scores, and feedback.
- Integrity signals are captured and exported to help instructors interpret results.

## Configuration & Extensibility

All operational “knobs” live in YAML so you can iterate quickly without code changes: model selection, token limits, prompt text, instructor lists, and other magic numbers. Prompt templates are versioned in `backend/config/prompts.yaml`, while general app behavior and limits live in `backend/config/config.yaml`. 
