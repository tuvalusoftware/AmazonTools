# PLAN-001 — C005: Docker — Container Image + Named Volume

← [plan001.main.md](plan001.main.md)

Packages the entire application as a single Docker container and mounts a named volume (`bsr_data`) at `/app/data` so the SQLite database and BSR snapshot files survive container restarts and image rebuilds.

**Depends on:** [plan001.C004_WebUI.todo.md](plan001.C004_WebUI.todo.md)

---

## `Dockerfile`

- [x] Create `Dockerfile` at repo root
- [x] Base image: `python:3.12-slim`
- [x] Set `WORKDIR /app`
- [x] Install system dependencies needed by Playwright (Chromium) in a single `RUN apt-get` layer:
  ```
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0
  libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2
  ```
  - Clean up `apt` cache in the same layer (`rm -rf /var/lib/apt/lists/*`)
- [x] Copy `requirements.txt` first; run `pip install --no-cache-dir -r requirements.txt`
- [x] Run `playwright install chromium --with-deps` in the same layer to cache browser binaries
- [x] Copy the rest of the source: `COPY . .`
- [x] Create the data directory inside the image as a placeholder: `RUN mkdir -p data`
  - The named volume will shadow this directory at runtime — the `mkdir` is only a safety net for local (non-Docker) runs
- [x] Declare a volume hint: `VOLUME ["/app/data"]`
- [x] Expose `ARG WEB_PORT=8080` and `EXPOSE $WEB_PORT`
- [x] Default `CMD ["python", "main.py"]`

---

## `docker-compose.yml`

- [x] Create `docker-compose.yml` at repo root
- [x] Use `services:` with a single service named `bsr-tracker`
- [x] `build: .` — build from the local `Dockerfile`
- [x] `restart: unless-stopped`
- [x] `ports: ["${WEB_PORT:-8080}:${WEB_PORT:-8080}"]`
- [x] `env_file: [.env]` — inject all secrets and config at runtime; `.env` is never baked into the image
- [x] `volumes: ["bsr_data:/app/data"]` — named volume mounted to the data directory
- [x] Declare the named volume at the top-level `volumes:` key:
  ```yaml
  volumes:
    bsr_data:
  ```
- [x] Add a comment above the volume explaining that SQLite (`tracker.db`) and BSR snapshot folders both live here

---

## `.dockerignore`

- [x] Create `.dockerignore` at repo root
- [x] Exclude the following to keep the image lean and secrets out of the build context:
  ```
  .venv/
  __pycache__/
  **/__pycache__/
  *.pyc
  *.pyo
  .env
  .env.*
  data/
  logs/
  .git/
  .cursor/
  plans/
  *.md
  ```

---

## `requirements.txt` — confirm Docker-safe deps

- [x] Confirm `fastapi` and `uvicorn[standard]` are present
- [x] Confirm `playwright` is present (already used by scraper)
- [x] Confirm `beautifulsoup4` is present (used by ASIN lookup)
- [x] Confirm `apscheduler` is present (used by cron jobs)
- [x] Pin all versions to avoid non-deterministic builds (`pip freeze > requirements.txt` after local install if not already pinned)

---

## `WEB_BASE_URL` for Docker deployments

- [x] Document in `.env.example` (or README note) that `WEB_BASE_URL` must be set to the **host-visible** address when running in Docker, e.g.:
  ```
  WEB_BASE_URL=http://localhost:8080   # local dev
  WEB_BASE_URL=http://192.168.1.10:8080  # LAN server
  ```
  This value is embedded in unsubscribe links inside emails — it must be reachable by the email recipient's browser.

---

## Verification

- [x] Run `docker compose build` — confirm image builds without errors
- [ ] Run `docker compose up -d` — confirm container starts; check `docker compose logs -f`
- [ ] Open `http://localhost:8080` in a browser — confirm registration form renders
- [ ] Register a book; query the volume: `docker compose exec bsr-tracker sqlite3 data/tracker.db "SELECT * FROM tracked_books;"` — confirm row inserted
- [ ] Run `docker compose restart bsr-tracker` — confirm data survives restart (volume persists)
- [ ] Run `docker compose down` then `docker compose up -d` — confirm data survives full container recreation
- [ ] Confirm `.env` is **not** present inside the image: `docker compose run --rm bsr-tracker cat .env` — should return "No such file"
- [ ] Confirm `data/` folder is **not** baked into the image: `docker compose run --rm bsr-tracker ls data/` before first volume mount shows empty or placeholder only
- [ ] Run `docker image ls` — confirm image size is reasonable (< 2 GB with Playwright Chromium)
  > **Note:** actual size is ~3.18 GB due to `scrapegraphai`'s full LangChain/LangGraph stack; the 2 GB target is not achievable without replacing that dependency.
