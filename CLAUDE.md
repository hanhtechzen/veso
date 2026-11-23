# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

LuckyVision: collects Vietnamese lottery results automatically, serves them over a REST API and realtime SSE, and publishes SEO pages and forecasts. Everything runs on one VPS with Docker Compose (`db` Postgres, `redis`, `api`, `worker`, `caddy`). Project docs are in Vietnamese: `README.md`, `HUONG-DAN-CHAY.md` (step-by-step run guide), `docs/README.md` (design), `docs/LuckyVision_PRD_v1_0.md`.

## Commands

Backend (Python 3.12, package `luckyvision` in `backend/`):

```bash
cd backend
pip install -e ".[dev]"
pytest -q                                   # CI runs exactly this
pytest tests/test_reconcile.py -q           # single file
pytest tests/test_scrapers.py -k minhngoc   # single test
```

Stack and admin CLI:

```bash
./start.ps1   # or start.sh: creates .env with a random admin token, builds, loads sample data
docker compose up -d --build
docker compose exec api python -m luckyvision.cli migrate
docker compose exec api python -m luckyvision.cli plan --date 2026-11-02
docker compose exec api python -m luckyvision.cli collect --draw mb-mb-2026-11-02
docker compose exec api python -m luckyvision.cli simulate-live --draw mn-tp-hcm-2026-10-26
docker compose exec api python -m luckyvision.cli probe-source minhngoc-web --draw mn-tp-hcm-2026-10-26
docker compose exec api python -m luckyvision.cli create-admin --username admin --name "Quản trị"
docker compose logs -f worker
```

Local URLs: site `http://localhost`, API docs `http://localhost/v1/docs`. Caddy routes `/v1/*` to `api` and everything else to the static `web/` directory.

## Architecture

- **Draw IDs** have the form `<region>-<station>-<YYYY-MM-DD>`, for example `mb-mb-2026-10-29`, `mn-tp-hcm-2026-10-26` or `vl-power655-2026-10-29`. The regions are `mb`, `mn`, the central region and `vl` (Vietlott).
- `luckyvision/domain/`: prize structures per game, validation and **multi-source reconciliation**. This layer is pure and has no DB access.
- `luckyvision/sources/`: source adapters registered in `registry.py`.
  - `fixture` (sample files, ignored when `APP_ENV=prod`).
  - `http_json`: a config-only provider. You add it with a row in `data_sources`, no code.
  - Scrapers subclass `scrape_base.ScrapeAdapter` and implement `fetch` + `parse` (see `minhngoc.py`). To add one, register it in `registry.py` and add sample HTML to `tests/test_scrapers.py`. Scrapers are disabled by default, respect robots.txt and are rate-limited.
- `luckyvision/collector/`: the pipeline fetches, stores the raw copy, then parses, validates and reconciles. It also includes `planner` (draw schedule), `live` (live tracking → SSE events `draw.started`, `prize.updated`, `draw.completed`, `draw.published`) and `probe`.
- **Publishing rule:** auto-publish happens when the number of agreeing sources is at least `MIN_SOURCES_BY_REGION` (default `vl:1`). Otherwise the draw goes to the admin review queue. Manual entries always start as pending verification. Editing a published result requires a reason and creates a new version, never an overwrite.
- `luckyvision/worker.py`: APScheduler background process running on Vietnam time.
- `luckyvision/api/`: FastAPI. Routes: public `/v1`, SSE stream, `/v1/auth` (with 2FA), `/v1/admin` (session login or `Authorization: Bearer` with `ADMIN_TOKENS`, which bypasses 2FA), `/v1/forecasts`, `/v1/ai`, tools export.
- `luckyvision/site/`: server-rendered Jinja2 SEO pages, sitemap and robots.
- `luckyvision/forecast/`: 5 forecast models, generated before each draw, then scored and backtested.
- `luckyvision/migrations/`: numbered SQL files (`NNN_name.sql`), applied by `cli migrate`. Add new schema as the next number.
- `web/`: static HTML with no build step. Includes the PWA (`sw.js`, manifest), `live.html`, `du-doan.html`, `admin.html` and `cong-cu/index.html`. All pages fetch real data from the API.

## Workflow (sub-agents in `.claude/agents/`)

For any bug fix or feature, run these in order:

1. **investigator** (read-only): find the relevant code, root cause and plan.
2. **testcase-writer**: write failing pytest cases in `backend/tests/` first.
3. **coder**: minimal change to make them pass. Never weaken tests.
4. **tester**: run targeted tests, then `pytest -q`. On failure, go back to the coder.

## Deployment

A push to `main` runs `.github/workflows/deploy.yml`: pytest, then SSH to the VPS (`/opt/luckey`), `git pull`, compose up with `docker-compose.prod.yml` (Cloudflare Tunnel, no open 80/443), and a forced recreate of `caddy` so it picks up Caddyfile changes. Requires Docker Compose ≥ 2.24 (uses `!reset`). Backup/restore scripts are in `deploy/`.
