# GitHub Auth Plan

## Goal
Add GitHub OAuth authentication to gate all access, enforce instructor-only CSV export, and associate all data with the authenticated user ID derived from GitHub identity and repo access.

## Auth Model (High Level)
- **Single sign-on** via GitHub OAuth (web flow).
- **Backend** issues a signed JWT after OAuth callback; frontend relies on HTTP-only cookies.
- **Instructor access** determined by GitHub username matched against a backend config list.
- **Repo access** verified using GitHub API with the app token to ensure the student granted read access to their repo.

## Data Model Changes
- **Use `users` as the canonical student table** (no separate `students` table).
- Update existing tables to include `user_id`:
  - repos.user_id (already present)
  - submissions.user_id (already present)
  - questions.user_id
  - answers.user_id
  - grades.user_id
  - integrity_events.user_id

## Backend Authentication Flow
1. **GET /auth/github**
   - Redirect to GitHub OAuth with `read:user` and `repo` scope.
2. **GET /auth/github/callback**
   - Exchange code for access token.
   - Fetch GitHub user profile.
   - Upsert user record (`users`).
   - Store access token encrypted at rest.
   - Issue a signed JWT and set an HTTP-only auth cookie.
3. **GET /auth/me**
   - Returns `{ authenticated: boolean, github_login, is_instructor }`.
4. **POST /auth/logout**
   - Clears auth cookie.

## Backend Authorization Rules
- **All API endpoints** require authentication (except `/auth/*`).
- **Instructor-only**: `/exports/submissions.csv` requires `is_instructor = true`.
- **Student-only**: submission/answer endpoints use `user_id` from JWT; never trust client-supplied IDs.

## Repo Access Check
- After login, student pastes repo URL.
- Backend verifies repo access via GitHub API using the user token:
  - Confirm repo exists.
  - Confirm authenticated user has access.
  - Confirm repo is personal (owner type = User) and owner login matches the authed GitHub login.
  - Confirm `permissions.pull` or equivalent.

## Frontend Auth Flow
- On app load:
  - Call `GET /auth/me`.
  - If unauthenticated, show **Sign in with GitHub** screen only.
- After sign-in:
  - Show repo submission form.
  - Submit repo URL -> `POST /repos/verify` (must be authenticated).
  - If verified, call `POST /submissions` to generate questions.
- Instructor users:
  - Show CSV export UI.
  - CSV link calls authenticated `GET /exports/submissions.csv`.

## Frontend/Backend Contract Updates
- **Repo Verification**: `POST /repos/verify`
  - Auth required.
  - Backend checks repo access using user token.
- **Submissions**: `POST /submissions`
  - Auth required.
  - Backend uses `user_id` from JWT, not from client.
- **Answers**: `POST /answers`
  - Auth required.
  - Backend uses `user_id` from JWT, not from client.
- **Exports**: `GET /exports/submissions.csv`
  - Auth required + instructor check.

## Security Notes
- Use HTTP-only, Secure cookies for JWTs.
- Store GitHub access tokens encrypted at rest.
- Rotate/expire JWTs; store minimal token data.
- Validate OAuth `state` to prevent CSRF.
- Strictly ignore any client-supplied `user_id`.
- Block CORS in production; allow only same-origin.
- Rate-limit auth and submission endpoints.

---

# Work Streams

## Frontend Work Stream (Sequential)
1. **Auth Gate UI**
   - On load, call `/auth/me` to determine auth state.
   - If not authenticated, render “Sign in with GitHub” screen only.
2. **Auth Redirect Handling**
   - Add “Sign in with GitHub” button linking to `/auth/github`.
   - Add optional “Sign out” in UI for logged-in users.
3. **Instructor Controls**
   - Read `is_instructor` from `/auth/me`.
   - Show CSV export button only for instructors.
4. **Repo Verification**
   - Use authenticated `POST /repos/verify` before submissions.
   - Handle “no access” errors explicitly.
5. **Submission + Answer Flow**
   - Continue using `/submissions` and `/answers` (auth required).
   - Do not send `user_id` in payloads.

## Backend Work Stream (Sequential)
1. **OAuth Setup**
   - Add GitHub OAuth config (client ID/secret, callback URL).
   - Implement `/auth/github`, `/auth/github/callback`, `/auth/me`, `/auth/logout`.
2. **Session + Token Storage**
   - Persist tokens in `oauth_tokens` keyed by `user_id` (encrypted at rest).
   - Issue JWTs and set secure HTTP-only cookies.
3. **User Table + Migrations**
   - Use `users` as the canonical student record.
   - Add `user_id` FKs to all relevant tables.
4. **Auth Middleware**
   - Require auth for all non-auth endpoints.
   - Validate JWT and inject `user_id` into request context.
5. **Instructor Authorization**
   - Load instructor usernames from backend config.
   - Gate `/exports/submissions.csv` on instructor role.
6. **Repo Access Check**
   - Update `/repos/verify` to check repo access using user token.
7. **Submission/Answer Ownership**
   - Update `/submissions` and `/answers` to use session `user_id`.
   - Enforce `question.submission.user_id == session.user_id`.

## Integration Notes
- Frontend assumes cookie-based JWT auth.
- Backend should return 401 for unauthenticated and 403 for unauthorized (e.g., non-instructor export).
- CORS blocked in production; allow dev origins only if needed.

---

## Quick Auth Flow Summary
1. Frontend calls `/auth/me`; if unauthenticated, show only “Sign in with GitHub.”
2. OAuth callback stores GitHub token (encrypted) and issues a JWT cookie.
3. Frontend proceeds to `/repos/verify` and `/submissions` using the JWT cookie.
4. Backend checks repo access and ownership with the stored GitHub token.
5. CSV export requires instructor role from config.
