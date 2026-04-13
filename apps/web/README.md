# Knowloop Web Frontend

This app is the Next.js frontend for Knowloop.

Current scope:

- shared console shell
- `/workspace` placeholder route
- `/ask` main three-pane layout

The frontend must follow these source-of-truth files from the repo root:

1. `DESIGN.md`
2. `SITE.md`
3. `component-rules.md`
4. `frontend-agent.md`
5. `docs/frontend/page-structures/*`

## Run

```powershell
cd C:\Users\wowjd\Desktop\Knowloop\apps\web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Verification

```powershell
cd C:\Users\wowjd\Desktop\Knowloop\apps\web
npm run lint
npm run build
```

## Environment

Optional local environment file:

```text
NEXT_PUBLIC_KNOWLOOP_API_BASE_URL=http://127.0.0.1:8000
```

`apps/web/.env.example` documents the same value.

