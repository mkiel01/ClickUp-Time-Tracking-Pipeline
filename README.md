# ClickUp Time Tracking Pipeline

**License:** This repository is **not** open source. Personal, non-commercial use is allowed. Commercial use, monetization, redistribution, and production use in paid products/services are prohibited. See [`LICENSE`](LICENSE) for full terms.

---

## Why I built this

I rely on ClickUp for personal task and time management, but the **built-in time tracking did not match how I wanted hours recorded and summarized**—and the **workflow I needed was either awkward in the product or gated behind paid tiers** (depending on how ClickUp changed features over time). Rather than fight the UI or pay for a bundle of features I did not need, I **built a small custom pipeline** tailored to my own categories and reporting style.

This project:

- **Syncs** tasks and durations from the ClickUp API into a **PostgreSQL** database I control.
- **Derives** weekly and monthly rollups the way I define them (folders, tags, planned vs actual hours).
- **Exports** rich **Excel** workbooks (and a **Streamlit** UI) so I can review habits and work blocks outside ClickUp.
- Optionally **pushes** outputs to **Google Drive** and reacts to **webhooks** for automation.

**Rough build period:** July–December 2025 (~3–4 months of evenings/weekends), iterated as my own needs evolved.

---

## What’s in the repos

- `database.py` — fetch tasks from ClickUp, upsert into Postgres (durations from task dates such as start/due, not ClickUp’s paid Time Tracking API).
- `folder_config.py` — folder name map, planned hours, productivity/enjoyment tags (single place to customize).
- `main.py` — Streamlit app plus Excel generation (planned vs actual, productivity vs enjoyment buckets). In the report section, **export and Google Drive actions appear above the preview table**; the folder filter still applies to both the workbook and the table.
- `weekly_summary.py` — monthly/weekly aggregation logic shared by the UI (parameterized SQL).
- `webhook/` — optional Flask receiver (`webhook/app.py`) and launcher (`webhook/main.py`) for task events.
- `tracked_time_update.py` — date-range sync from the ClickUp task API into Postgres (CSV snapshot before upsert), using the same duration rules as the full fetch.
- `styling.py` — Excel formatting (including folder tag colors driven by `folder_config.py`).
- Docker + `docker-compose` for a repeatable local run (Postgres client in the image for optional `pg_dump` backups).

### CI

GitHub Actions (`.github/workflows/ci.yml`) runs on pushes and PRs to `main` / `master`: `compileall` on the Python modules plus `python -m unittest discover -s tests` (no API keys required).

### Daily automation

GitHub Actions workflow: `.github/workflows/daily-pipeline.yml` (`runs-on: self-hosted` on your Mac).

| Step | Command |
|------|---------|
| 1 | `python tracked_time_update.py --days-back 2` |
| 2 | `python main.py export -o habbit_tracker.xlsx` |
| 3 | `python drive_upload.py habbit_tracker.xlsx` |

Uses local `.env`, `.venv`, **`service_account.json`** (preferred) or `token.pickle` — **no GitHub Secrets**. Set `GOOGLE_DRIVE_FILE_ID` in `.env` so the pipeline updates one Sheet; Streamlit upload still creates a new file each time unless `file_id` is passed.

**Paths on this Mac:**

| What | Path |
|------|------|
| Project (workflow runs here) | `~/Desktop/click_up_api` |
| Runner (install here — **not** inside the project, **not** on Desktop) | `~/actions-runners/clickup` |
| Service logs | `~/Library/Logs/actions.runner.mkiel01-ClickUp-Time-Tracking-Pipeline.Michals-MacBook-Pro/` |

**Runner as background service:** `./svc.sh install` + `./svc.sh start` — **not** `./run.sh`. macOS blocks LaunchAgents from **Desktop** (`Operation not permitted` in `stderr.log`). The project stays on Desktop; the runner lives in `~/actions-runners/clickup`.

#### Clean install (self-hosted runner)

**1 — GitHub (browser)**

- **Settings → Actions → Runners**
- Remove any old **Offline** runner (⋯ → Remove)
- **New self-hosted runner** → **macOS + ARM64**
- Keep the page open — you need the **Download** and **Configure** commands (token expires in ~1 hour)

**2 — Mac: remove old runner completely**

```bash
# stop service (ignore errors if already gone)
cd ~/Desktop/click_up_api/actions-runner/clickup 2>/dev/null && ./svc.sh stop && ./svc.sh uninstall
cd ~/actions-runners/clickup 2>/dev/null && ./svc.sh stop && ./svc.sh uninstall
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/actions.runner.mkiel01-ClickUp-Time-Tracking-Pipeline.Michals-MacBook-Pro.plist 2>/dev/null
rm -f ~/Library/LaunchAgents/actions.runner.mkiel01-ClickUp-Time-Tracking-Pipeline.Michals-MacBook-Pro.plist

# delete old installs
rm -rf ~/Desktop/click_up_api/actions-runner
rm -rf ~/actions-runners/clickup
```

**3 — Mac: fresh download** (paste **Download** block from GitHub into `~/actions-runners/clickup`)

```bash
mkdir -p ~/actions-runners/clickup
cd ~/actions-runners/clickup
# curl + tar from GitHub page (must be osx-arm64, not x64)
```

**4 — Mac: register + start service** (paste **Configure** line from GitHub)

```bash
cd ~/actions-runners/clickup
./config.sh --url https://github.com/mkiel01/ClickUp-Time-Tracking-Pipeline --token YOUR_TOKEN_FROM_GITHUB
# Enter for every prompt
./svc.sh install
./svc.sh start
./svc.sh status
```

**5 — Verify**

```bash
tail -10 ~/Library/Logs/actions.runner.mkiel01-ClickUp-Time-Tracking-Pipeline.Michals-MacBook-Pro/stderr.log
tail -10 ~/Library/Logs/actions.runner.mkiel01-ClickUp-Time-Tracking-Pipeline.Michals-MacBook-Pro/stdout.log
```

- `stderr.log`: no `Operation not permitted`
- `stdout.log`: `Listening for Jobs`
- GitHub → Runners → **Idle**

**Run pipeline:** Actions → **Daily pipeline** → **Run workflow** (or push to `main`, or daily **18:00 Warsaw** / `0 16 * * *` UTC in summer). Mac must be awake.

Trigger from terminal (after `brew install gh && gh auth login`):

```bash
cd ~/Desktop/click_up_api
gh workflow run "Daily pipeline"
gh run watch
```

**Manual (same steps, no Actions):**

```bash
cd ~/Desktop/click_up_api
set -a && source .env && set +a
.venv/bin/python tracked_time_update.py --days-back 2
.venv/bin/python main.py export -o habbit_tracker.xlsx
.venv/bin/python drive_upload.py habbit_tracker.xlsx
```

Use **`.venv/bin/python`** — this venv has no `python` shim on PATH.

#### Lessons learned (Jun 2026 — don’t repeat)

**Self-hosted runner**

| Mistake | What actually works |
|--------|----------------------|
| Runner inside `click_up_api/actions-runner/` on **Desktop** | Runner at **`~/actions-runners/clickup`** only |
| `./run.sh` for daily automation | **`./svc.sh install`** + **`./svc.sh start`** (background) |
| `./run.sh` to “test” then wonder why svc fails | `./run.sh` in Terminal **can** work on Desktop; **`svc.sh` cannot** — different macOS rules |
| GitHub page **x64** on Apple Silicon | **ARM64** download |
| `config.sh remove` when runner vanished from GitHub | Delete local files: `rm -f .runner .credentials .credentials_rsaparams` + new token |
| Old `macos/github-actions-runner.plist` | **Ignore** — obsolete; `svc.sh install` creates its own LaunchAgent plist |
| `stderr.log` still shows Desktop errors after fix | Old lines stay in the file — read **latest** `stdout.log` (`Listening for Jobs`) |

**Verify runner:** GitHub → Runners → **Idle**; `stdout.log` ends with `Listening for Jobs`; no new `Operation not permitted` in `stderr.log`.

**Google Drive (step 3 — `drive_upload.py`)**

| Mistake | What actually works |
|--------|----------------------|
| User OAuth (`token.pickle`) for **scheduled** pipeline | **`service_account.json`** — no browser, no expiry |
| Not sharing the Sheet with the SA email | Share Sheet with SA email as **Editor** |
| **Web application** OAuth client (Streamlit fallback) | **Desktop app** → `oauth_client.json` with `"installed"` |
| `python` after `source .venv/bin/activate` | **`.venv/bin/python`** |
| Committing the SA JSON | Already gitignored — never commit keys |

**Daily pipeline auth:** put `service_account.json` in the project root (from GCP → service account → Keys → JSON). Share the Sheet with that SA’s email.

**Postgres (pipeline step 1)** — on Mac host, not in Docker for daily pipeline:

```bash
brew services start postgresql@17
pg_isready -h 127.0.0.1 -p 5432
# .env: POSTGRES_HOST=127.0.0.1
```

**What “working end-to-end” looks like (verified Jun 2026):** self-hosted runner **Idle** at `~/actions-runners/clickup` → `gh workflow run "Daily pipeline"` → all three steps green including Google Sheet upload.


## Personalized setup note

This project is personalized for my own workflow. Some parts are intentionally hardcoded (for example folder/category names, preferred order in reports, planned hours, tags, and fixed report date ranges). Lists are not fully dynamic by default.

If you want to use it for your own personal workflow, start with **`folder_config.py`** and **`main.py`** (date ranges, folder order in Excel), plus **`styling.py`** for Excel colors.

### Google Drive upload

`google_auth.py` prefers **`service_account.json`** (daily pipeline / headless). If missing, falls back to Desktop user OAuth + `token.pickle` (Streamlit).

**Files (project root, gitignored):**

| File | Role |
|------|------|
| `service_account.json` | **Preferred** — GCP service account key (pipeline) |
| `oauth_client.json` | Desktop OAuth client (optional fallback) |
| `token.pickle` | User OAuth token (optional fallback) |

**Service account setup:**

1. GCP → Service accounts → create → Keys → JSON → save as `service_account.json`
2. Enable [Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com?project=habbittrackerapi)
3. Share the Google Sheet with the SA email as **Editor**
4. Set **`GOOGLE_DRIVE_FILE_ID`** in `.env`

**Test upload (no browser):**

```bash
cd ~/Desktop/click_up_api
set -a && source .env && set +a
.venv/bin/python drive_upload.py habbit_tracker.xlsx
```

User OAuth fallback still works if `service_account.json` is absent (browser login). Docker: mount `service_account.json` (or generate `token.pickle` on the host).


### GitHub “Traffic” / clones

GitHub does **not** show *who* cloned the repo. A spike in **clones** with few **unique visitors** often means `git clone`/API/automation (mirrors, scrapers, CI) rather than people clicking the repo page—it is not something you can attribute to “bots vs humans” from the dashboard alone.

## Local setup with `.env`

1. Create your local env file:
   - copy `.env.example` to `.env`
2. Fill in required values:
   - `CLICKUP_API_KEY`
   - `CLICKUP_TEAM_ID`
   - PostgreSQL variables (`POSTGRES_*`)
   - webhook DB variables (`WEBHOOK_POSTGRES_*`) if you use webhook scripts

`.env` is gitignored and should never be committed.

## Run with Docker

```bash
docker compose up --build
```

Streamlit app will be available at:
- [http://localhost:8501](http://localhost:8501)

## Run without Docker

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run main.py
```

## Security checklist before making repo public

- Rotate any API key that was ever hardcoded in past commits.
- Ensure `.env`, `oauth_client.json`, `service_account.json`, and `token.pickle` are not tracked.
- If secrets were committed before, clean git history before publishing.

### Database backups

**CSV (table `clickup_mkiel` only)** — `database_backup_csv/`

- **Full fetch** (`database.py`): CSV snapshot before sync.
- **Range upsert** (`tracked_time_update`): CSV before upsert.
- **Manual**: Streamlit CSV backup button, or `python database.py backup`.

**pg_dump (whole database)** — `database_backup_pg/`, custom format (`.dump`)

- Runs automatically after the CSV step on **full fetch** (if `pg_dump` is available). Set **`SKIP_PG_DUMP=1`** in `.env` to skip (e.g. no client tools on the host).
- **Manual**: Streamlit pg_dump backup button, or `python database.py backup-pg`.
- **Restore** (example; use your DB name and empty target or new DB):

  ```bash
  pg_restore -h localhost -p 5432 -U USER -d clickup --clean --if-exists path/to/clickup_YYYYMMDD_HHMMSS.dump
  ```

Docker image includes **`postgresql-client`** so `pg_dump` works in the container. Compose mounts **`./database_backup_pg`** like the CSV folder.

