# NightCrate frontend

React/TypeScript with Vite, MUI Community, D3, Zustand and TanStack Query.
Shared instructions: [CLAUDE.md](../CLAUDE.md).

From the repository root, `make dev` starts both servers. For the frontend alone:

```bash
npm install
npm run dev
npm run build   # TypeScript checks and production bundle
npm run lint
```

Run these commands from `frontend/`. Vite proxies `/api`, `/docs`, and
`/openapi.json` to the local backend. Keep requests same-origin for LAN/tablet
access; see the root [README](../README.md#access-model).

- `src/pages/`, `src/components/`: screens and shared views.
- `src/api/`: typed HTTP clients.
- `src/stores/`, `src/lib/`: state and shared utilities.
- `src/theme/`: MUI light/dark themes.

Feature constraints, including persistent pages, planner state and tablet
interaction, are in [development decisions](../docs/development-decisions.md).
There is currently no frontend test script.
