# Auto Research Pro Max

Auto Research Pro Max is a local-first research workspace for turning an idea into a paper-grounded plan, getting explicit approval on that plan, and tracking staged execution in one web interface. The goal is not to hide the workflow behind a black-box agent run, but to make planning, grounding, and progress visible.

## Demo

![Auto Research Pro Max screenshot](./page-long.png)

## What It Does

- Collect a mandatory project brief before execution: title, idea, background, direction, goals, constraints, and must-read papers.
- Combine local PDF uploads and remote paper URLs in the same project workspace.
- Generate a research plan first, then require explicit approval before any run starts.
- Execute the current staged workflow with live stage tracking and persisted outputs.
- Configure OpenAI / Codex-compatible settings and test the connection from the GUI.
- Review papers, plans, runs, and stage outputs in one modern web dashboard.
- Share the app over LAN for demos, reviews, or screenshots from another device.

## Current Stage Plan

The current product is temporarily set to 10 stages plus a planning gate. More stages will be added in later iterations as the workflow, retrieval stack, and execution system become more complete.

## Requirements

- `macOS` for the current one-click launcher flow
- `Python 3.11+`
- `Node.js 18+` and `npm`
- internet access on first launch so Python and frontend dependencies can be installed
- an OpenAI-compatible API key if you want live model outputs instead of local fallback outputs

Windows one-click support: Coming Soon.

## Stack

- Backend: `FastAPI`, `SQLite`, `OpenAI Python SDK`, `pypdf`
- Frontend: `React`, `TypeScript`, `Vite`

## One-click start

On macOS, double-click [`start.command`](start.command).

Before using the one-click launcher, make sure you have:

- `Python 3.11+`
- `Node.js 18+` and `npm` available in your shell `PATH`
- internet access on first launch so dependencies can be installed
- optional: an OpenAI-compatible API key for live model-backed planning and stage generation

Windows one-click support: Coming Soon.

That launcher will:

- create `.venv` if needed
- install backend dependencies
- install frontend dependencies if missing
- build the frontend bundle
- start the backend on `http://127.0.0.1:8000`
- open the app in your browser

To stop the background server later, double-click [`stop.command`](stop.command).

If no API key is configured, the app still runs with deterministic fallback outputs so the GUI and workflow remain usable.

## LAN sharing

If you want to open the app from another device on the same local network, double-click [`start-lan.command`](start-lan.command).

That mode binds the server to `0.0.0.0` and prints one or more `LAN URL` addresses in the terminal window. Open one of those URLs from your PC browser.

If your Mac prompts for firewall access, allow it or the PC may not be able to connect.

## Manual run

### 1. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
uvicorn backend.app.main:app --reload
```

The backend starts on `http://127.0.0.1:8000`.

### 2. Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend starts on `http://127.0.0.1:5173`.

## Current Workflow

1. Configure API settings.
2. Create a project with title, idea, background, direction, goals, and constraints.
3. Attach must-read papers through local PDF upload or remote URLs.
4. Generate the plan.
5. Review and approve the plan.
6. Start the reduced pipeline and watch stage output update live.

## Privacy And Local-first Behavior

- Project metadata, plans, run state, stage outputs, and settings are stored locally in `backend/data/app.db`.
- Uploaded PDFs are stored locally in `backend/data/uploads/`.
- Remote paper URLs are fetched over the network when you add them, and remote PDFs are downloaded locally when possible.
- If an API key is configured, project context, paper snippets, approved plans, and prior stage outputs are sent to the configured model endpoint.
- If no API key is configured, the app uses local fallback outputs and does not make model API calls.
- API settings are currently stored locally in SQLite for convenience in this prototype; there is no separate secrets vault yet.

## Architecture

- [`frontend/`](frontend) contains the React + TypeScript + Vite web UI.
- [`backend/app/`](backend/app) contains the FastAPI API, project state endpoints, plan generation, and run orchestration.
- [`backend/data/`](backend/data) holds the local SQLite database and uploaded paper files.
- [`launcher.py`](launcher.py) and the `*.command` scripts provide one-click local and LAN startup flows.
- WebSocket updates stream run progress to the GUI while stages are executing.

## Current Limitations

- The current workflow is still a 10-stage pipeline plus a planning gate, not the final expanded stage system.
- Literature retrieval is still centered on user-provided PDFs and URLs; live scholarly search adapters are not integrated yet.
- Execution is still prototype-level and does not yet use a hardened experiment sandbox.
- Final export, citation verification, branching, and richer review loops are still in progress.
- Windows one-click startup is not available yet.

## Roadmap

- Expand the current stage pipeline with more granular stages as the product matures.
- Add retrieval adapters for `OpenAlex`, `Semantic Scholar`, `Crossref`, and `arXiv`.
- Add a real experiment sandbox with better runtime control and artifact capture.
- Add export pipelines for `Markdown`, `LaTeX`, and compiled `PDF`.
- Add bibliography generation, citation verification, and claim-evidence checks.
- Add first-class Windows support, including one-click start/stop scripts and packaging.

More planned work is tracked in [`TODO.md`](TODO.md).

## FAQ / Troubleshooting

- `python3: command not found`
  Install Python `3.11+` and make sure `python3` is available in your shell.
- `npm: command not found`
  Install `Node.js` so both `node` and `npm` are available in your shell.
- The first launch feels slow
  The launcher may be creating `.venv`, installing Python packages, installing frontend dependencies, and building the frontend bundle.
- My PC cannot open the app over the network
  Start with [`start-lan.command`](start-lan.command), make sure both devices are on the same LAN, and allow macOS firewall access if prompted.
- I did not configure an API key
  That is supported. The app will still run, but plan and stage outputs will use deterministic local fallback content instead of live model calls.

## License

This project is licensed under [`AGPL-3.0`](LICENSE). If you modify the software and provide it over a network, the corresponding source code obligations still apply.

## Contributing

Issues and focused pull requests are welcome. For larger workflow or architecture changes, open an issue first so the stage model, UI flow, and product direction can be aligned before implementation.
