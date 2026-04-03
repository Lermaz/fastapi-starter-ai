# FastAPI Videogames API

Production-style FastAPI baseline with:

- **Liveness** `GET /health` (no DB) and **readiness** `GET /ready` (DB `SELECT 1`)
- Versioned API under **`/api/v1`** (e.g. `/api/v1/auth/login`, `/api/v1/videogames`)
- JWT auth (access + refresh with rotation + revocation); optional **httpOnly refresh cookie** + **`X-CSRF-Token`** for browser flows (`AUTH_REFRESH_COOKIE_ENABLED`)
- permissions matrix in code (`videogame:read`, `videogame:write`, `user:manage_roles`) mapped from roles `admin` / `user`
- videogame CRUD
- Alembic migrations
- CLI to seed an admin user (`python -m app.cli create-admin`)
- GitHub Actions CI (Ruff, Alembic, pytest; Python 3.11–3.13 matrix; concurrency + least-privilege permissions)
- Dependabot for `pip` and GitHub Actions
- Production-oriented settings checks (`ENVIRONMENT=production` requires a strong JWT; warns on SQLite)
- CORS from `CORS_ORIGINS` (explicit origins only — **never `*`** with `allow_credentials=True`) and SlowAPI rate limits on `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/refresh`
- **Trusted hosts** (`ALLOWED_HOSTS`), **security headers** (optional **HSTS** via `SECURITY_ENABLE_HSTS`), **`X-Request-ID`**, JSON **error envelope** (`error.code`, `message`, `request_id`, `detail`)
- OpenAPI/Swagger **off by default in production**; set `ENABLE_OPENAPI=true` to expose `/docs`, `/redoc`, `/openapi.json`
- **DB pool** tuning for non-SQLite URLs (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, …)

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
- `ALLOWED_HOSTS`, `API_V1_PREFIX`, `ENABLE_OPENAPI`, `SECURITY_ENABLE_HSTS`, `AUTH_REFRESH_COOKIE_ENABLED`, and pool variables — see [`.env.example`](.env.example).

Middleware runs **TrustedHost → request ID → security headers → CORS** (CORS registered last so it is outermost on the request path, per Starlette ordering).

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

If that email already exists (e.g. from a prior `POST /api/v1/auth/register`), promote and reset password:

```bash
python -m app.cli create-admin --email admin@example.com --password "new-password" --force
```

Run migrations **before** the CLI so tables exist.

## 5) Run the API

```bash
uvicorn main:app --reload
```

Docs (when OpenAPI is enabled for the current environment):

- Swagger UI: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>

Use `create_app()` / `create_app(Settings(...))` from [`app/main.py`](app/main.py) if you need a second app instance (e.g. tests with different settings).

## 6) Auth, permissions, and roles

### Register

`POST /api/v1/auth/register`

- Always creates `user` (never auto-admin).

### Login

`POST /api/v1/auth/login`

Uses OAuth2 form:

- `username` = email
- `password` = password

Returns:

- `access_token`
- `refresh_token` (omitted when `AUTH_REFRESH_COOKIE_ENABLED=true`; then a **httpOnly** cookie is set and `csrf_token` is returned for `X-CSRF-Token` on cookie-based refresh/logout)

### Refresh token rotation

`POST /api/v1/auth/refresh`

- Verifies JWT signature + type + token version
- Verifies stored hashed refresh token
- Rotates to a new refresh token (old one becomes invalid)
- Accepts refresh **cookie first** (with valid CSRF header when using the cookie), else JSON body `refresh_token` (native clients)

### Logout / revocation

`POST /api/v1/auth/logout`

- Clears stored refresh token hash
- Increments `token_version`
- Invalidates existing access and refresh tokens for that user

### Current user

`GET /api/v1/auth/me`

Requires Bearer access token.

### Permission matrix (code)

Defined in `app/core/permissions.py`:

| Role  | Permissions                                              |
| ----- | -------------------------------------------------------- |
| admin | `videogame:read`, `videogame:write`, `user:manage_roles` |
| user  | `videogame:read`                                         |

Routes use `require_permission(...)` in `app/core/dependencies.py`.

### Change another user’s role

`PATCH /api/v1/auth/users/{user_id}/role`

Body:

```json
{
  "role": "admin"
}
```

Requires `user:manage_roles` (admins have it by default).

## 7) Videogame endpoints

All endpoints require Bearer token.

- `GET /api/v1/videogames` — `videogame:read`
- `GET /api/v1/videogames/{videogame_id}` — `videogame:read`
- `POST /api/v1/videogames` — `videogame:write`
- `PATCH /api/v1/videogames/{videogame_id}` — `videogame:write`
- `DELETE /api/v1/videogames/{videogame_id}` — `videogame:write`

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
2. **test** — matrix **Python 3.11, 3.12, 3.13**; installs app + dev deps; `alembic upgrade head`; **`pytest`** with **`pytest-cov`** on package **`app`** (minimum **70%** line coverage per [`pyproject.toml`](pyproject.toml)) plus OpenAPI smoke tests (`/openapi.json`, `/docs`).

**Dependabot:** [`.github/dependabot.yml`](.github/dependabot.yml) opens weekly PRs for `pip` and `github-actions`, with **`target-branch: dev`** (PRs merge into `dev` first).

Local parity (after `alembic upgrade head` so `/ready` can hit the DB):

```bash
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
ruff check app alembic main.py tests
ruff format --check app alembic main.py tests
pytest -q
```

To run tests **without** the coverage gate (faster while iterating): `pytest -q --no-cov`.

Configuration: [`ruff.toml`](ruff.toml). Pytest + coverage options live in [`pyproject.toml`](pyproject.toml) (`pythonpath`, `addopts` with `--cov=app` and `--cov-fail-under=70`, `[tool.coverage.*]`). Coverage **omits** `app/core/*` and empty `app/__init__.py` (core is exercised indirectly via router tests).

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
    middleware/
      request_id.py
      security_headers.py
    permissions.py
    request_context.py
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
  helpers.py
  integration/
    test_auth_and_permissions.py
    test_auth_router.py
    test_auth_cookie_refresh.py
    test_openapi.py
    test_openapi_production.py
    test_smoke.py
    test_videogames_router.py
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
- **`ALLOWED_HOSTS`** must include the `Host` value your reverse proxy forwards.
- **`ENABLE_OPENAPI=true`** if you want `/docs` in production (default is off).
- **`AUTH_REFRESH_COOKIE_ENABLED`** for SPA cookie refresh; keep **`AUTH_COOKIE_SECURE=true`** behind HTTPS.

### Tests

Pytest sets high auth rate limits and `ENVIRONMENT=development` in [`tests/conftest.py`](tests/conftest.py) before importing the app so the suite stays fast and deterministic. Integration-style API tests live under [`tests/integration/`](tests/integration/); shared non-fixture helpers are in [`tests/helpers.py`](tests/helpers.py).
