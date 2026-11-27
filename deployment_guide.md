# Deployment guide – Streamlit Community Cloud

How the public demo of Deal-Prep Copilot is deployed and run (Phase 6, D39 §4).

## What runs where

- **Streamlit Community Cloud** runs `app.py` (repo root). The agents, research and RAG code run inside the same Python process (`backend/` is put on `sys.path` by `app.py`).
- **Supabase** (dev project) holds the knowledge base, saved briefings, run logs and the demo daily counter.
- **Gemini** (free tier) for the models and embeddings, **Tavily** for web research. All keys stay server-side in Streamlit Secrets and never reach the browser.

## Demo mode

| Visitor | What they can do | Quota used |
|---|---|---|
| No access code | Read the sample briefings (`briefings.is_sample = true`) in the sidebar; the newest one opens on the first screen | none |
| With the access code | Run a live research run, see the briefings from their own session | ~2 Gemini flash calls + up to 20 Tavily credits (Standard depth, D37) per run |

- **Access code:** `DEMO_ACCESS_CODE`. Compared in constant time, kept for the browser session after one correct entry.
- **Daily cap:** `DEMO_DAILY_CAP` live runs per day for the whole site (default 4), counted in the Supabase table `demo_usage` by `claim_demo_run(cap)` (atomic, so parallel visitors can't go over the cap). The day is the **Pacific date**, so the cap resets with the Gemini quota at midnight Pacific (10:00 Israel time in winter). A run is counted when it starts, even if it fails later.
- **Fail closed:** demo mode is on unless `DEMO_MODE=off`. With demo mode on and no `DEMO_ACCESS_CODE`, live runs are disabled. If the counter can't be reached, live runs are disabled.

## First deploy

1. **Database:** apply the migrations to the Supabase project (`supabase db push` from the repo root, linked project). Phase 6 adds `20261111120000_demo_usage.sql`.
2. **Sample briefings:** run 3–4 briefings locally (`DEMO_MODE=off streamlit run app.py`), then from `backend/`:
   ```
   python mark_sample.py --list            # find the briefing IDs
   python mark_sample.py <briefing_id>     # mark as sample (repeat per briefing)
   python mark_sample.py <briefing_id> --off
   ```
3. **Push** the reviewed commits to GitHub (Cloud deploys from the repo).
   **Keepalive secrets:** in the GitHub repo, *Settings → Secrets and variables → Actions*, add `SUPABASE_URL` and `SUPABASE_KEY` (same values as `.env`). Then *Actions → Supabase keepalive → Run workflow* once and check it ends green with `HTTP 200`.
4. **Create the app** on [share.streamlit.io](https://share.streamlit.io): sign in with GitHub, give access to the repo, *Create app* → repository, branch `main`, main file `app.py`.
5. **Advanced settings:** Python **3.12**. Paste the secrets (TOML, root level, no section headers):
   ```toml
   GEMINI_API_KEY = "..."
   TAVILY_API_KEY = "..."
   SUPABASE_URL = "https://<project-ref>.supabase.co"
   SUPABASE_KEY = "..."          # secret (service_role) key: server-side only
   SUPABASE_ANON_KEY = "..."
   DEMO_ACCESS_CODE = "..."      # long random string; share on request
   DEMO_DAILY_CAP = "4"
   # optional overrides (defaults in backend/app/core/config.py)
   # CHAT_MODEL = "gemini-3.5-flash"
   # CHAT_MODEL_SMALL = "gemini-3.5-flash-lite"
   ```
   Don't set `TAVILY_CACHE_DIR` (live results) or `DEMO_MODE` (on by default).
6. **Deploy** and wait for the install (`requirements.txt`). `app.py` copies root-level secrets into environment variables for `core/config.py` if Cloud hasn't already.
7. **Check** (record in `TESTING.md` §4):
   - without a code: the sample list and a sample briefing (one Hebrew, RTL)
   - wrong code → "Wrong access code", nothing counted
   - set `DEMO_DAILY_CAP = "0"` → "Today's live-run limit is reached"; set it back
   - one live run with the code; the sidebar shows "Live runs today: 1 / 4"

## Everyday operations

- **Any change in Secrets** (rotating `DEMO_ACCESS_CODE`, changing `DEMO_DAILY_CAP`, fixing a key) takes effect only after **Manage app → ⋮ → Reboot app**: saving reruns the script, but the values were already copied into environment variables and the database connection is cached. Sessions that already entered the old code need the new one after the reboot.
- **Add / remove a sample:** `python mark_sample.py <id>` / `--off` (locally, with the service key in `.env`). No redeploy needed. Don't mark a briefing that shows "Written by the fallback model" (written by flash-lite after a 503 or flash's daily quota).
- **See today's count:** the sidebar line for code holders, or in Supabase: `select * from demo_usage order by day desc;`
- **Reset today's count** (e.g. after testing): `update demo_usage set runs = 0 where day = public.demo_day();`
- **Sleep:** free apps sleep after a period without visitors; the first visit wakes them (about a minute).
- **Supabase pausing:** Free-plan projects are paused after about a week with too little database activity (happened 2026-11-24). The workflow `.github/workflows/supabase-keepalive.yml` calls the read-only `demo_runs_today()` every Monday and Thursday (06:00 UTC). If the project is already paused, the call fails and GitHub emails the failed run: restore the project in the Supabase dashboard (*Restore project*, about 3 minutes until the API answers; restorable for 90 days). In a **public** repo GitHub disables scheduled workflows after 60 days without repository activity: re-enable it on the Actions page or with `gh workflow enable "Supabase keepalive"`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "The daily model quota (Gemini free tier) is used up" | 20 flash requests per model per day. Wait for 10:00 Israel time, or lower `DEMO_DAILY_CAP`. The log line `daily quota details:` has the quota ID and retry delay. |
| "Written by the fallback model" above a briefing | Flash was overloaded (`503 UNAVAILABLE`, Google-side) or out of its daily quota; the small model wrote it (the run's stage detail says which). Normal; try again later (after 10:00 Israel time for the quota) for the usual wording. |
| "Live research runs are turned off on this deployment" | `DEMO_ACCESS_CODE` is missing in Secrets. |
| "Live runs are unavailable right now (the usage counter can't be reached)" | Supabase unreachable, or the `demo_usage` migration isn't applied. |
| Sidebar: "Briefing history is unavailable" | `SUPABASE_URL` / `SUPABASE_KEY` / `SUPABASE_ANON_KEY` missing or wrong in Secrets. |
| `Missing environment variables in .env: …` in the Cloud log | A required secret is missing (the message says `.env`, but on Cloud it means Secrets). |
| Install fails or is slow | Use a slim requirements file (without `fastapi`, `uvicorn`, `pytest`) and point the app to it. |

## Security notes

- The service key is only in Secrets and in the local `.env`; both are outside git (`.env`, `.streamlit/secrets.toml` are in `.gitignore`).
- The UI doesn't use Supabase Auth (D39 §3). Visitors never get a database token; all queries run server-side.
- Public visitors only see briefings marked as samples. A code holder also sees the briefings of their own session's runs, never other visitors' runs.
