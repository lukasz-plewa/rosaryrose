# Rosary Rose — Web Application

A web app for managing a "Rosary Rose" (Polish: *Róża Różańcowa*) —
a Catholic prayer group of 20 people who each pray one of the 20 mysteries
of the Rosary, rotating to the next mystery every month.

The app generates monthly assignment tables (PNG images) and tracks the
roster over time, so historical compositions of the rose are preserved
when members change.

> **Note:** the user interface (HTML, error messages) is in Polish, since
> this is a tool built for Polish prayer groups. The codebase, comments,
> and docs are in English so the project can be understood by anyone.

## Features

- Login by password or Google OAuth
- Multiple leaders, each managing their own roses (data isolation)
- Single admin (configured by email in env) who approves new accounts
  and can view all roses
- Open registration with admin approval gate
- Configurable via environment variables
- Dockerfile + Railway deployment

## Architecture

```
roza_v3/
├── Dockerfile                  # production image
├── railway.toml                # Railway.app deployment config
├── .env.example                # ENV template
├── DEPLOY.md                   # step-by-step deployment guide
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI - rose endpoints
│       ├── config.py           # reads ENV
│       ├── models.py           # User, Rose, Person, RoseMembership
│       ├── auth.py             # bcrypt, JWT, FastAPI dependencies
│       ├── auth_endpoints.py   # /api/auth/*, /api/admin/users/*
│       ├── users_service.py    # user CRUD + approval logic
│       ├── services.py         # rose CRUD + temporal composition
│       ├── rotation.py         # mystery rotation logic
│       └── renderer.py         # PNG generator (Pillow)
└── frontend/
    └── index.html              # SPA with login, roses list, admin panel
```

## Domain concepts

A **Rose** has 20 numbered positions (1..20). Each position holds one
**Person**. On a fixed day each month (e.g. 25th), all positions advance
to the next of the 20 rosary mysteries (Joyful 1..5, Light 1..5,
Sorrowful 1..5, Glorious 1..5). Some months may be excluded from rotation
(typically July & August summer break).

A **RoseMembership** is a temporal record: "person X holds position Y from
date A to date B" (B may be NULL, meaning still current). This preserves
history when the roster changes — if you reassign position 5 in October,
the previous occupant in September is still recorded.

## Local development

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example .env
# Edit .env - set ADMIN_EMAIL to your email, and a SECRET_KEY
python -m uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000` and:

1. Click "Rejestracja" (Register)
2. Use the email you set as `ADMIN_EMAIL` — this account is auto-approved
   and granted admin role
3. Create a rose, add people, assign them to positions

## Roles

- **Admin** (single account, email matches `ADMIN_EMAIL`): sees all roses,
  has the user approval panel.
- **Leader** (any other registered account): sees only their own roses.
  Newly registered leaders must be approved by the admin before they can do
  anything in the app.

## Google OAuth (optional)

To enable Google sign-in:

1. Go to https://console.cloud.google.com/apis/credentials
2. Create "OAuth 2.0 Client ID" of type "Web application"
3. Under "Authorized redirect URIs" add:
   - `http://127.0.0.1:8000/api/auth/google/callback` (dev)
   - `https://your-app.up.railway.app/api/auth/google/callback` (prod)
4. Copy Client ID and Client Secret into `.env`:
   ```
   GOOGLE_CLIENT_ID=...
   GOOGLE_CLIENT_SECRET=...
   BASE_URL=https://your-app.up.railway.app
   ```

A first-time Google login creates a new (pending) user account, unless
the Google email matches `ADMIN_EMAIL` (then auto-approved). If a local
password account with the same email already exists, Google is linked to it.

## Production deployment

See **[DEPLOY.md](DEPLOY.md)** for the full step-by-step guide.

In short: we deploy to Railway.app with auto-deploy from GitHub. Every
`git push` to `main` triggers a rebuild and deploy.

What you need:
- GitHub account (public repo is fine)
- Railway.app account (sign in with GitHub)
- ~5 minutes for the initial setup

## API

Interactive docs: `https://your-domain/docs`

### Public
- `POST /api/auth/register` — register
- `POST /api/auth/login` — log in with password
- `POST /api/auth/logout` — log out
- `GET /api/auth/me` — current user info
- `GET /api/auth/google/login` — redirect to Google OAuth
- `GET /api/auth/google/callback` — OAuth callback

### Approved users
- `GET /api/roses` — list roses (filtered by owner)
- `POST /api/roses` — create rose
- `GET, PUT, DELETE /api/roses/{id}` — rose operations (owner-scoped)
- `GET, POST /api/roses/{id}/persons` — persons in rose
- `PUT, DELETE /api/persons/{id}` — person edit/delete
- `GET /api/roses/{id}/composition?at=YYYY-MM-DD` — composition on a date
- `PUT /api/roses/{id}/composition/{pos}` — assign position
- `GET /api/roses/{id}/positions/{pos}/history` — position history
- `GET /api/roses/{id}/month?year=&month=` — month data
- `GET /api/roses/{id}/png?year=&month=[&year_to=&month_to=]` — PNG

### Admin only
- `GET /api/admin/users` — list all users
- `GET /api/admin/users/pending` — pending accounts
- `POST /api/admin/users/{id}/approve` — approve account
- `DELETE /api/admin/users/{id}` — reject (pending accounts only)

## Roadmap

Next planned phase: email notifications when mysteries rotate
(per-rose SMTP config, automatic monthly emails to members).
