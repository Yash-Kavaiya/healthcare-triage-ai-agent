# Healthcare Triage AI Agent

Safety-first triage platform that combines a FastAPI backend, Angular UI, and a shared triage engine with scheduling, queueing, and auditability.

## Highlights

- FastAPI backend with JWT auth, triage intake, queue workflow, dashboards, and audit endpoints.
- Angular control center UI with intake, nurse queue, dashboard, and audit views.
- Shared engine for routing policy, scheduling/preemption, notifications, and SQLite persistence.

## Architecture

- Backend API: `backend/app/main.py`
- Frontend UI: `frontend/src/app`
- Domain engine: `triage_agent/`
- Tests: `tests/`

## Quickstart

### Backend

Install Python deps:

```bash
pip install -r requirements.txt
```

Run the API (two options):

```bash
python app.py
```

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs:

- `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
npm install
npm start
```

Frontend runs at `http://localhost:4200` (or the next available port if 4200 is busy).

The dev server uses a proxy (`frontend/proxy.conf.json`) so `/api/*` calls reach the backend without CORS setup.

## Authentication

All `/api/v1/*` endpoints require `Authorization: Bearer <JWT>` except `POST /api/v1/auth/login`.

Default users (forced password change on first login):

- `admin / admin123` (`admin`)
- `nurse / nurse123` (`nurse`)
- `ops / ops123` (`operations`)

Role enforcement:

- `queue` read/write: `nurse`, `admin`
- `triage intake`: `operations`, `nurse`, `admin`
- `dashboard`: `operations`, `nurse`, `admin`
- `audit`: role scope taken from JWT claim (client cannot choose arbitrary role)

Optional auth configuration:

- `TRIAGE_AUTH_SECRET=...`
- `TRIAGE_AUTH_ALGORITHM=HS256`
- `TRIAGE_AUTH_EXPIRES_MINUTES=30`
- `TRIAGE_AUTH_REFRESH_EXPIRES_MINUTES=10080`
- `TRIAGE_AUTH_LOGIN_MAX_ATTEMPTS=5`
- `TRIAGE_AUTH_LOGIN_WINDOW_SECONDS=300`
- `TRIAGE_AUTH_LOGIN_LOCKOUT_SECONDS=900`
- `TRIAGE_AUTH_FORCE_CHANGE_DEFAULTS=true`
- `TRIAGE_AUTH_USERS_JSON=[{"username":"admin","password":"admin123","role":"admin"}]`

`POST /api/v1/auth/login` applies per-username and per-source-IP lockout. When locked, the API returns `429` with `Retry-After`.

## Reasoner Modes

The backend uses `TRIAGE_REASONER_MODE=hybrid` by default:

- `heuristic`
- `openai`
- `hybrid` (OpenAI with heuristic fallback)

To use OpenAI mode/hybrid:

```bash
set OPENAI_API_KEY=your_key_here
set TRIAGE_OPENAI_MODEL=gpt-4o-mini
```

Optional:

- `TRIAGE_OPENAI_TIMEOUT_SECONDS=20`
- `TRIAGE_OPENAI_MAX_OUTPUT_TOKENS=500`

## Notifications

Escalations can trigger webhook/email/SMS hooks:

- `TRIAGE_NOTIFICATIONS_ENABLED=true`
- `TRIAGE_NOTIFY_ON_URGENCIES=EMERGENCY,URGENT`
- `TRIAGE_NOTIFICATION_WEBHOOK_URL=https://...`
- `TRIAGE_EMAIL_WEBHOOK_URL=https://...`
- `TRIAGE_NOTIFICATION_EMAIL_TO=a@x.com,b@y.com`
- `TRIAGE_SMS_WEBHOOK_URL=https://...`
- `TRIAGE_NOTIFICATION_SMS_TO=+15551230001,+15551230002`
- `TRIAGE_NOTIFICATION_TIMEOUT_SECONDS=6`
- `TRIAGE_NOTIFICATION_FAIL_OPEN=true`

## API Surface

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/change-password`
- `POST /api/v1/auth/logout`
- `POST /api/v1/triage/intake`
- `GET /api/v1/queue`
- `POST /api/v1/queue/{queue_id}/book`
- `GET /api/v1/dashboard/metrics`
- `GET /api/v1/dashboard/appointments`
- `GET /api/v1/dashboard/activity`
- `GET /api/v1/audit`
- `GET /health`

`GET /api/v1/dashboard/metrics` returns slot utilization, queue pressure, triage volume, urgency mix, auto-book/preemption counts, and repeat-patient load.

## Tests

```bash
pytest -q
```

Frontend production build:

```bash
cd frontend
npm run build
```
