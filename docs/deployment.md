# TraceWeave web deployment

The web app is a Next.js standalone build. It deliberately includes a local
Case 1 dataset, so `npm run dev` works before an API is available. Set
`NEXT_PUBLIC_API_URL` at build time (or in Compose) to enable API loading from
`GET /cases`; if the request fails, the UI keeps the demo visible and reports
the fallback in its status line.

## Local development

```bash
cd web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

For a fresh offline-friendly local setup, run `./setup.sh` (or
`.\setup.ps1` on Windows), then `./start.sh` (or `.\start.ps1`). These start
the API and Next.js development server as separate local processes; Docker is
not required.

The deterministic scenario fixture writes logs only and never opens the
application database:

```bash
python -m datasets.generator --output datasets/generated
python -m datasets.generator --clock-skew 5 --drop-source-window --identity-conflict
```

Each run creates `auth.jsonl`, `application.audit`, `network.csv`, and
`ground_truth.json` in the selected output directory.

## Compose

From the repository root, run `docker compose up --build`. The API is exposed
on port 8000 and the web app on port 3000. `Dockerfile.api` packages the `api`
module and exposes `api.app:app`. Mount a persistent volume at
`/app/.traceweave-data` for a long-running installation.
