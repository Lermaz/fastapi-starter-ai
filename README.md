# FastAPI Videogames API

Production-style FastAPI baseline with:

- healthcheck (`/health`)
- JWT auth (access + refresh with rotation + revocation)
- permissions matrix in code (`videogame:read`, `videogame:write`, `user:manage_roles`) mapped from roles `admin` / `user`
- videogame CRUD
- Alembic migrations
- CLI to seed an admin user (`python -m app.cli create-admin`)
- GitHub Actions CI (Ruff, Alembic, pytest; Python 3.11–3.13 matrix; concurrency + least-privilege permissions)
- Dependabot for `pip` and GitHub Actions
- Production-oriented settings checks (`ENVIRONMENT=production` requires a strong JWT; warns on SQLite)
- CORS from `CORS_ORIGINS` and SlowAPI rate limits on `/auth/register`, `/auth/login`, `/auth/refresh`

## 1) Requirements

- Python 3.11+ (3.12+ recommended for CI parity)
- Virtual environment (`.venv`)

## 2) Setup

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

For linting and tests (optional locally; matches CI):

```bash
pip install -r requirements-dev.txt
```

Create env file:

```bash
copy .env.example .env
```

Set a strong value for `JWT_SECRET_KEY` in `.env` (at least **32 characters** if you set `ENVIRONMENT=production`).

Optional in `.env`:

- `CORS_ORIGINS` — comma-separated list (e.g. `http://localhost:3000`). Empty = no CORS middleware.
- `AUTH_REGISTER_RATE_LIMIT`, `AUTH_LOGIN_RATE_LIMIT`, `AUTH_REFRESH_RATE_LIMIT` — SlowAPI strings such as `10/minute` (defaults are set in [`app/core/config.py`](app/core/config.py)).

## 3) Database migration (Alembic)

Create/update schema:

```bash
alembic upgrade head
```

Rollback one revision:

```bash
alembic downgrade -1
```

Create a new migration after model changes:

```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## 4) Bootstrap an admin (CLI)

Public registration creates users with role `user` only. Create the first admin locally:

```bash
python -m app.cli create-admin --email admin@example.com --password "your-secure-password"
```

If that email already exists (e.g. from a prior `POST /auth/register`), promote and reset password:

```bash
python -m app.cli create-admin --email admin@example.com --password "new-password" --force
```

Run migrations **before** the CLI so tables exist.

## 5) Run the API

```bash
uvicorn main:app --reload
```

Docs:

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

## 6) Auth, permissions, and roles

### Register

`POST /auth/register`

- Always creates `user` (never auto-admin).

### Login

`POST /auth/login`

Uses OAuth2 form:

- `username` = email
- `password` = password

Returns:

- `access_token`
- `refresh_token`

### Refresh token rotation

`POST /auth/refresh`

- Verifies JWT signature + type + token version
- Verifies stored hashed refresh token
- Rotates to a new refresh token (old one becomes invalid)

### Logout / revocation

`POST /auth/logout`

- Clears stored refresh token hash
- Increments `token_version`
- Invalidates existing access and refresh tokens for that user

### Current user

`GET /auth/me`

Requires Bearer access token.

### Permission matrix (code)

Defined in `app/core/permissions.py`:

| Role   | Permissions                                      |
|--------|--------------------------------------------------|
| admin  | `videogame:read`, `videogame:write`, `user:manage_roles` |
| user   | `videogame:read`                                 |

Routes use `require_permission(...)` in `app/core/dependencies.py`.

### Change another user’s role

`PATCH /auth/users/{user_id}/role`

Body:

```json
{
  "role": "admin"
}
```

Requires `user:manage_roles` (admins have it by default).

## 7) Videogame endpoints

All endpoints require Bearer token.

- `GET /videogames` — `videogame:read`
- `GET /videogames/{videogame_id}` — `videogame:read`
- `POST /videogames` — `videogame:write`
- `PATCH /videogames/{videogame_id}` — `videogame:write`
- `DELETE /videogames/{videogame_id}` — `videogame:write`

List supports:

- `offset` (default `0`)
- `limit` (default `20`, max `100`)
- optional filters: `genre`, `platform`

## 8) CI (GitHub Actions)

Workflow: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

**Triggers:** push and pull request to `main`, `master`, `dev`, and `qa`, plus **workflow_dispatch** (manual run from the Actions tab).

**Hardening:**

- `permissions: contents: read` (least privilege)
- **Concurrency:** new runs for the same ref cancel in-progress runs (saves minutes on busy PRs)

**Jobs:**

1. **lint** — Python 3.12, installs only [`requirements-dev.txt`](requirements-dev.txt) (pinned **Ruff**), runs `ruff check` and `ruff format --check` on `app`, `alembic`, `main.py`, `tests`.
2. **test** — matrix **Python 3.11, 3.12, 3.13**; installs app + dev deps; `alembic upgrade head`; **`pytest`** (`tests/`: smoke, auth/login, permission denial, admin videogame CRUD, refresh rotation).

**Dependabot:** [`.github/dependabot.yml`](.github/dependabot.yml) opens weekly PRs for `pip` and `github-actions`, with **`target-branch: dev`** (PRs merge into `dev` first).

Local parity (after `alembic upgrade head` so `/health` can hit the DB):

```bash
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
ruff check app alembic main.py tests
ruff format --check app alembic main.py tests
pytest -q
```

Configuration: [`ruff.toml`](ruff.toml). Pytest discovers tests from [`pyproject.toml`](pyproject.toml) (`pythonpath = ["."]`) so imports work even when your IDE runs tests with a non-repo-root working directory.

[`tests/conftest.py`](tests/conftest.py) points the app at a **temporary SQLite file** and **`JWT_SECRET_KEY`** for isolation, runs **`create_all`** once per session, and **truncates** `users` / `videogames` after each test. You do **not** need `alembic upgrade` before `pytest` (CI still runs Alembic to validate migrations).

**Branch protection:** configure on GitHub for `main`, `dev`, and `qa` (not in YAML). See [`.github/branch-protection.md`](.github/branch-protection.md) for steps and required check names.

## 9) Project layout

```text
app/
  cli/
    __main__.py
  core/
    config.py
    dependencies.py
    errors.py
    limiter.py
    permissions.py
    security.py
  db/
    session.py
  models/
    user.py
    videogame.py
  routers/
    auth.py
    health.py
    videogames.py
  schemas/
    auth.py
    videogame.py
alembic/
  env.py
  versions/
.github/
  workflows/
    ci.yml
  branch-protection.md
  dependabot.yml
tests/
  conftest.py
  test_auth_and_permissions.py
  test_smoke.py
main.py
pyproject.toml
requirements-dev.txt
ruff.toml
```

## 10) Notes

- Schema changes are managed with Alembic (not `create_all` at runtime).
- Keep secrets only in `.env` (never commit `.env`).

### Production (`ENVIRONMENT=production` or `prod`)

- App startup **fails** if `JWT_SECRET_KEY` is empty, a known default, or shorter than 32 characters.
- A **warning** is emitted if `DATABASE_URL` still uses SQLite (use Postgres/MySQL in real deployments).
- Configure **`CORS_ORIGINS`** for your frontend; rate limits apply per client IP (in-memory store — use Redis-backed limiting if you scale horizontally).

### Tests

Pytest sets high auth rate limits and `ENVIRONMENT=development` in [`tests/conftest.py`](tests/conftest.py) before importing the app so the suite stays fast and deterministic.
