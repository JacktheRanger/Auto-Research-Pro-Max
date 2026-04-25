# Cloudflare Deployment Recipe

Auto Research Pro Max splits cleanly into a static frontend (Vite build) and
a FastAPI backend. The recipe below ships the frontend on **Cloudflare Pages**
and exposes the backend through **Cloudflare Tunnel**, so the only public
endpoint is on the Cloudflare edge while the API runs wherever you can keep a
process up (a VPS, a Mac mini, a Raspberry Pi, …).

## 1. Frontend on Cloudflare Pages

1. Create a new Pages project from the same Git repository.
2. Configure the build:
   - **Framework preset**: `None`
   - **Build command**: `bash deploy/cloudflare-pages-build.sh`
   - **Build output directory**: `frontend/dist`
   - **Root directory**: leave empty (build runs from repo root).
3. Add an environment variable `API_BASE_URL` that points at the public API
   tunnel (see step 2). The build script writes the value into a runtime
   `frontend/public/runtime-config.json` so the SPA can pick it up.
4. Trigger a deploy. Cloudflare Pages will publish `frontend/dist` to a
   `*.pages.dev` URL and any custom domain you bind.

The default Pages preview only serves static files, so all `/api/*` calls
must be routed back to your FastAPI host (next step).

## 2. Backend via Cloudflare Tunnel

1. On the host that will run the backend (Linux server, Mac mini, Pi):
   ```bash
   docker compose -f deploy/docker-compose.yml up -d --build
   ```
   The container listens on `127.0.0.1:8000` (or whatever
   `AUTO_RESEARCH_PORT` is set to).
2. Install the Cloudflare Tunnel client (`cloudflared`) and authenticate it:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create auto-research-api
   ```
3. Create a tunnel config (`~/.cloudflared/config.yml`):
   ```yaml
   tunnel: <tunnel-id>
   credentials-file: /home/<user>/.cloudflared/<tunnel-id>.json

   ingress:
     - hostname: api.example.com
       service: http://localhost:8000
     - service: http_status:404
   ```
4. Route the hostname through the tunnel and start it:
   ```bash
   cloudflared tunnel route dns auto-research-api api.example.com
   cloudflared tunnel run auto-research-api
   ```
   For long-running deployments, install `cloudflared` as a system service
   (`cloudflared service install`).

## 3. Wire the SPA to the tunneled API

`deploy/cloudflare-pages-build.sh` emits `frontend/public/runtime-config.json`
during the Pages build:

```json
{
  "apiBaseUrl": "https://api.example.com"
}
```

If your fork does not need a separate domain (e.g. you just bind the same
domain to both Pages and the tunnel using subpaths), leave `API_BASE_URL`
empty and the SPA will keep using same-origin fetches.

## 4. Hardening checklist

- Enable **Cloudflare Access** in front of `api.example.com` if the workflow
  isn't meant for the public internet.
- Set `CORS_ALLOWED_ORIGINS` (env var, see `backend/app/main.py`) once you
  pin the deployed origin instead of `*`.
- Mount only the directories you trust into the container. Drop the
  `/var/run/docker.sock` mount if the host should not let the sandbox stage
  spawn sibling containers.
- Schedule regular backups of `deploy/data/` (SQLite + uploaded papers).
