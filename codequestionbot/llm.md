# Lane C Progress (LLM Orchestration + Grading Security)

## Context Check
- Reviewed `PLAN.md` to align with Lane C scope.
- Lane B uses YAML config + prompts; Lane C is aligned and wired into `backend/llm/interface.py`.

## Tasks and Status
1. Question-generation prompt
   - Completed.
   - Prompts stored in `backend/config/prompts.yaml` and rendered by `backend/llm/module.py`.
   - Updated guidance to prioritize assignment-specific/unique snippets and diverse coverage.
2. Snippet selector prompt
   - Completed.
   - Updated guidance to prefer unique, assignment-specific logic, ensure diverse coverage, and target 10-20 line methods (minimum 5-10 lines).
2. Grader prompt + JSON schema
   - Completed.
   - Grader prompt in `backend/config/prompts.yaml`; schemas built in `backend/llm/module.py`.
3. Scoring rubric + confidence normalization
   - Completed.
   - Normalization helpers in `backend/llm/module.py`; thresholds in `backend/config/config.yaml`.
4. LLM output validation logic
   - Completed.
   - Schema-based validation in `backend/llm/module.py` with numeric coercions.
5. Rate limits, retries, safe error handling
   - Completed.
   - Defaults in `backend/config/config.yaml`.
6. LLM interface wiring
   - Completed.
   - HTTP-backed OpenAI calls, response validation, snippet caps, and fallbacks in `backend/llm/interface.py`.

## Decisions
- **Config format**: YAML to align with Lane B (`backend/config/config.yaml`, `backend/config/prompts.yaml`).
- **Schema enforcement**: `backend/llm/module.py` validates types, bounds, and enums for LLM output.
- **Fallbacks**: If `OPENAI_API_KEY` is missing or LLM fails, use deterministic fallback questions/grades.

## Implementation Notes
- `backend/llm/interface.py` uses YAML config for LLM settings (model, retries, rate limit) and supports snippet caps.
- Questions map `snippet_index` to stored snippet metadata; grades use stored excerpt context only.

## Files Added or Updated
- `backend/config/prompts.yaml` holds prompt templates.
- `backend/config/config.yaml` includes categories, grading bounds, and LLM settings.
- `backend/llm/module.py` exposes prompt builders, schema validation, and normalization.
- `backend/llm/interface.py` handles OpenAI calls and fallbacks.

## Tests
- `backend/tests/test_llm_interface.py` covers fallback behavior.
