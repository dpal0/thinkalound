# Development

## Frontend
```bash
cd frontend
bun install
bun run dev
```

## Backend
```bash
cd backend
export OPENAI_API_KEY=your_key_here
export DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/codequestionbot
export GITHUB_CLIENT_ID=your_github_oauth_client_id
export GITHUB_CLIENT_SECRET=your_github_oauth_client_secret
export GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback
export JWT_SECRET=replace_with_a_long_random_string
export TOKEN_ENCRYPTION_KEY=replace_with_fernet_key
export AUTH_REDIRECT_URL=http://localhost:5173
uv sync
uv run python -m app.main
```

### GitHub OAuth Setup (Local)
1. Go to https://github.com/settings/developers -> OAuth Apps -> New OAuth App.
2. Homepage URL: `http://localhost:5173`
3. Authorization callback URL: `http://localhost:8000/auth/github/callback`
4. Copy the Client ID/Secret into the env vars above.

### Generate TOKEN_ENCRYPTION_KEY
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Migrations (Production-Friendly)
When you add columns, use a migration tool instead of wiping data.
1. Add Alembic: `uv pip install alembic`
2. Initialize: `alembic init alembic`
3. Create a revision: `alembic revision --autogenerate -m "add new columns"`
4. Review the generated script, then apply: `alembic upgrade head`
