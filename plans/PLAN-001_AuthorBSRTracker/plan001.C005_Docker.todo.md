# PLAN-001 — C005: Docker — Container Image + Named Volume

← [plan001.main.md](plan001.main.md)

Packages the entire application as a single Docker container and mounts a named volume (`bsr_data`) at `/app/data` so the SQLite database and BSR snapshot files survive container restarts and image rebuilds.

**Depends on:** [plan001.C004_WebUI.todo.md](plan001.C004_WebUI.todo.md)

---

## `Dockerfile`

- [ ] Create `Dockerfile` at repo root
- [ ] Base image: `python:3.12-slim`
- [ ] Set `WORKDIR /app`
- [ ] Install system dependencies needed by Playwright (Chromium) in a single `RUN apt-get` layer:
  ```
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0
  libxcomposite1 libxdamage1 libxrandr2 libgbm1 libasound2
  ```
  - Clean up `apt` cache in the same layer (`rm -rf /var/lib/apt/lists/*`)
- [ ] Copy `requirements.txt` first; run `pip install --no-cache-dir -r requirements.txt`
- [ ] Run `playwright install chromium --with-deps` in the same layer to cache browser binaries
- [ ] Copy the rest of the source: `COPY . .`
- [ ] Create the data directory inside the image as a placeholder: `RUN mkdir -p data`
  - The named volume will shadow this directory at runtime — the `mkdir` is only a safety net for local (non-Docker) runs
- [ ] Declare a volume hint: `VOLUME ["/app/data"]`
- [ ] Expose `ARG WEB_PORT=8080` and `EXPOSE $WEB_PORT`
- [ ] Default `CMD ["python", "main.py"]`

---

## `docker-compose.yml`

- [ ] Create `docker-compose.yml` at repo root
- [ ] Use `services:` with a single service named `bsr-tracker`
- [ ] `build: .` — build from the local `Dockerfile`
- [ ] `restart: unless-stopped`
- [ ] `ports: ["${WEB_PORT:-8080}:${WEB_PORT:-8080}"]`
- [ ] `env_file: [.env]` — inject all secrets and config at runtime; `.env` is never baked into the image
- [ ] `volumes: ["bsr_data:/app/data"]` — named volume mounted to the data directory
- [ ] Declare the named volume at the top-level `volumes:` key:
  ```yaml
  volumes:
    bsr_data:
  ```
- [ ] Add a comment above the volume explaining that SQLite (`tracker.db`) and BSR snapshot folders both live here

---

## `.dockerignore`

- [ ] Create `.dockerignore` at repo root
- [ ] Exclude the following to keep the image lean and secrets out of the build context:
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

- [ ] Confirm `fastapi` and `uvicorn[standard]` are present
- [ ] Confirm `playwright` is present (already used by scraper)
- [ ] Confirm `beautifulsoup4` is present (used by ASIN lookup)
- [ ] Confirm `apscheduler` is present (used by cron jobs)
- [ ] Pin all versions to avoid non-deterministic builds (`pip freeze > requirements.txt` after local install if not already pinned)

---

## `WEB_BASE_URL` for Docker deployments

- [ ] Document in `.env.example` (or README note) that `WEB_BASE_URL` must be set to the **host-visible** address when running in Docker, e.g.:
  ```
  WEB_BASE_URL=http://localhost:8080   # local dev
  WEB_BASE_URL=http://192.168.1.10:8080  # LAN server
  ```
  This value is embedded in unsubscribe links inside emails — it must be reachable by the email recipient's browser.

---

## Verification

- [ ] Run `docker compose build` — confirm image builds without errors
- [ ] Run `docker compose up -d` — confirm container starts; check `docker compose logs -f`
- [ ] Open `http://localhost:8080` in a browser — confirm registration form renders
- [ ] Register a book; query the volume: `docker compose exec bsr-tracker sqlite3 data/tracker.db "SELECT * FROM tracked_books;"` — confirm row inserted
- [ ] Run `docker compose restart bsr-tracker` — confirm data survives restart (volume persists)
- [ ] Run `docker compose down` then `docker compose up -d` — confirm data survives full container recreation
- [ ] Confirm `.env` is **not** present inside the image: `docker compose run --rm bsr-tracker cat .env` — should return "No such file"
- [ ] Confirm `data/` folder is **not** baked into the image: `docker compose run --rm bsr-tracker ls data/` before first volume mount shows empty or placeholder only
- [ ] Run `docker image ls` — confirm image size is reasonable (< 2 GB with Playwright Chromium)
