# FastAPI Videogames API

Production-style FastAPI baseline with:

- healthcheck (`/health`)
- JWT auth (access + refresh with rotation + revocation)
- permissions matrix in code (`videogame:read`, `videogame:write`, `user:manage_roles`) mapped from roles `admin` / `user`
- videogame CRUD
- Alembic migrations
- CLI to seed an admin user (`python -m app.cli create-admin`)
- GitHub Actions CI (Ruff + Alembic upgrade)

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

Create env file:

```bash
copy .env.example .env
```

Set a strong value for `JWT_SECRET_KEY` in `.env`.

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

Workflow: `.github/workflows/ci.yml`

On push/PR to `main` or `master`:

- `ruff check` + `ruff format --check` on `app`, `alembic`, `main.py`
- `alembic upgrade head` against a temporary SQLite URL (`DATABASE_URL` in the workflow)

Local parity:

```bash
pip install ruff
ruff check app alembic main.py
ruff format --check app alembic main.py
```

Configuration: `ruff.toml`.

## 9) Project layout

```text
app/
  cli/
    __main__.py
  core/
    config.py
    dependencies.py
    errors.py
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
main.py
ruff.toml
```

## 10) Notes

- Schema changes are managed with Alembic (not `create_all` at runtime).
- Keep secrets only in `.env` (never commit `.env`).
