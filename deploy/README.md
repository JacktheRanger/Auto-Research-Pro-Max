# Deployment Recipes

Auto Research Pro Max ships two reference deployments:

- **Self-hosted Docker** — a single container that bundles the FastAPI
  backend and the prebuilt Vite frontend. Suitable for VPS / on-prem boxes.
- **Cloudflare Pages + Tunnel** — push the static SPA to Cloudflare Pages
  and proxy `/api/*` to a backend host via Cloudflare Tunnel.

## Docker (`Dockerfile` + `docker-compose.yml`)

```bash
# from the repository root
docker compose -f deploy/docker-compose.yml up --build
```

The compose file persists `backend/data/` to `deploy/data/` on the host so
SQLite, paper uploads, and sandbox artifacts survive restarts. By default it
also mounts the host Docker socket so the experiment sandbox stage can spin
up sibling containers; remove that line if your environment forbids it.

Override the host port with `AUTO_RESEARCH_PORT`. OCR is enabled by
installing `tesseract-ocr` inside the image; drop the apt step if you do not
need it.

## Cloudflare (`cloudflare.md`)

`cloudflare.md` walks through publishing the frontend on **Cloudflare Pages**
and exposing the FastAPI backend through **Cloudflare Tunnel**. The
`cloudflare-pages-build.sh` script installs frontend deps, optionally writes
a `runtime-config.json` with `API_BASE_URL`, and runs `npm run build` so
Pages ends up serving `frontend/dist`.

Both recipes are intentionally lightweight — adapt them to your hosting,
secrets, and access policies before going to production.
