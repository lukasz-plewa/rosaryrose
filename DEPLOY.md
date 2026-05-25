# Deploying to Railway.app

Step-by-step guide for the first deployment, plus how to publish
subsequent versions.

---

## Part 1: Initial deployment

### Step 1: Push the code to GitHub

In the `roza_v3/` directory:

```bash
git init
git add .
git commit -m "Phase 3 - web application with authentication"
```

Create a new **public** repo on https://github.com (e.g. `rosary-rose`)
and link your local repo:

```bash
git remote add origin https://github.com/YOUR_LOGIN/rosary-rose.git
git branch -M main
git push -u origin main
```

**Important**: thanks to the bundled `.gitignore`, your `.env` (with
secrets) and `roza.db` (the database file) will NOT be pushed to the
public repo. After the first push, double-check on GitHub: if you see
`.env` or any `*.db` files in the repo, remove them and reach out — we
need to fix that.

### Step 2: Sign up for Railway

Go to https://railway.app and sign up using "Login with GitHub". Railway
will ask for permission to access the chosen repo — grant it.

Under **Plans** check the available free credits (typically $5 trial,
no card required initially).

### Step 3: Create a project from the repo

1. Click **"New Project"** on the dashboard
2. Choose **"Deploy from GitHub repo"**
3. Pick `rosary-rose`
4. Railway will start building the Dockerfile automatically

The first deploy takes ~2-3 min (build + start). It may end with an error
because secrets aren't set yet — that's OK, we'll fix it in the next step.

### Step 4: Add a volume for SQLite

This is critical — without a volume, the database is lost on every redeploy.

1. In the project, click the service tile (named after your repo)
2. Go to **"Settings"** → section **"Volumes"**
3. Click **"+ New Volume"**
4. Mount path: `/data`
5. Size: `1 GB` (overkill — actual usage is a few MB)
6. Save

### Step 5: Set environment variables (secrets)

In the same service, go to **"Variables"**:

Click **"+ New Variable"** and add the following:

| Name | Value |
|---|---|
| `ADMIN_EMAIL` | your email (the one you'll register the admin account with) |
| `SECRET_KEY` | a random string — generate via `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DATABASE_URL` | `sqlite:////data/roza.db` (four slashes!) |
| `COOKIE_SECURE` | `true` |
| `BASE_URL` | will fill in next step |

### Step 6: Generate a public URL

**"Settings"** → section **"Networking"** → **"Generate Domain"**.

Railway will assign an address like
`rosary-rose-production-abc123.up.railway.app`.

Back to **"Variables"** and add:

| Name | Value |
|---|---|
| `BASE_URL` | `https://rosary-rose-production-abc123.up.railway.app` (your URL) |

After saving, Railway will auto-redeploy.

### Step 7: Verify it works

After ~30s open your URL. You should see the login screen.

Register with the email you set in `ADMIN_EMAIL` → that account becomes
admin automatically. Now you can create roses.

### Step 8 (optional): Google OAuth

If you want Google sign-in:

1. Go to https://console.cloud.google.com/apis/credentials
2. **"Create Credentials"** → **"OAuth 2.0 Client ID"** → **"Web application"**
3. **"Authorized redirect URIs"**: add `https://your-url.up.railway.app/api/auth/google/callback`
4. Copy **Client ID** and **Client Secret**
5. In Railway, add variables:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`

The app will redeploy and the "Sign in with Google" button will start working.

---

## Part 2: Deploying new versions

After the first deploy, Railway watches the `main` branch of your GitHub
repo. Every `git push` = automatic redeploy.

### Standard cycle

```bash
# 1. Edit code locally
# 2. Run locally to verify it works:
cd backend
uvicorn app.main:app --reload --port 8000

# 3. When it works - commit:
cd ..  # back to repo root
git add .
git status                       # check what you're committing
git commit -m "Brief description"
git push

# 4. Open Railway → Deployments tab → you'll see a new build
#    After ~1-2 min the changes are live
```

### Good practice: feature branches

To avoid deploying half-done work straight to production:

```bash
# Work on a separate branch
git checkout -b new-feature
# ... edit ...
git push origin new-feature

# When it works locally, merge into main:
git checkout main
git merge new-feature
git push   # <- this triggers the deploy
```

Railway only deploys `main` by default. Other branches live on GitHub
without affecting production.

### When a deploy fails

In Railway, **"Deployments"** tab → click the failed deploy → **"View Logs"**.
Common issues:

- **Build failed**: typo in `Dockerfile` or missing library in `requirements.txt`
- **Crashed on start**: Python error at startup — logs show the stack trace
- **Healthcheck failed**: app starts but `/docs` doesn't respond within 30s

You can roll back to a previous version with one click:
**"Deployments"** → next to an older, working deploy → **"Redeploy"**.

### Database backup

The SQLite file lives on the volume. To grab a copy:

```bash
# Install Railway CLI (once):
npm i -g @railway/cli
railway login

# In the project directory, link to your Railway project:
railway link

# Stream the file out of the container:
railway run cat /data/roza.db > roza-backup-$(date +%Y%m%d).db
```

Open the resulting file in **DB Browser for SQLite** (GUI for inspecting
SQLite databases).

### Restoring from backup

In case of a screw-up, to push an older database back:

```bash
# Pause the service in Railway (Settings → Pause)
# Push the file:
railway run bash -c "cat > /data/roza.db" < roza-backup-20260601.db
# Resume the service
```

---

## Part 3: Monitoring and cost

### Cost on Railway

The free trial gives a one-time $5 credit. After that, a small service
like this is typically ~$3-5/month (Railway charges per minute for
CPU/RAM/network). For reference — an always-running service that's used
just once a month is roughly 256 MB RAM × 730 h × the rate ≈ $3/mo.

You can set a monthly cap under **Account → Usage Limits**.

### Logs and metrics

**"Metrics"** tab shows CPU/RAM/network usage over time.
**"Logs"** tab is the live application log.

### Pausing the service

If you won't use it for a few months, **"Settings" → "Danger" → "Pause"**
the service (zero cost, data preserved on the volume). Resume to bring
everything back online.

---

## Common problems

**Q: After deploy I see "Application failed to respond"**
A: Check `Logs` — usually a missing env variable or Python error.

**Q: After redeploy the data is gone**
A: The volume isn't mounted at `/data`, or `DATABASE_URL` doesn't have
four slashes. Verify: `Settings → Volumes` and `Variables → DATABASE_URL=sqlite:////data/roza.db`.

**Q: Google OAuth returns "redirect_uri_mismatch"**
A: In Google Cloud Console, the URL under "Authorized redirect URIs"
must **exactly** match `BASE_URL` + `/api/auth/google/callback`,
including `https://` and no trailing slash.

**Q: After pushing to GitHub, Railway doesn't deploy**
A: Check `Settings → Source → Auto Deploy` — must be enabled.
