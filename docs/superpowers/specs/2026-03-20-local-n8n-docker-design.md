# Local n8n + MCP Server Docker Setup

## Goals

- **Dev convenience:** Iterate on workflows locally without deploying to n8n Cloud
- **Cost:** Self-host instead of paying for n8n Cloud
- **Full autonomy:** Claude Code can create/modify/trigger n8n workflows programmatically via MCP

## Architecture

Two long-running containers + one one-shot seeder on a shared Docker network:

```
┌─────────────────────────────────────────────────┐
│  docker-compose (network: council-net)           │
│                                                  │
│  ┌──────────────┐       ┌────────────────────┐  │
│  │  n8n          │       │  n8n-mcp            │  │
│  │  port 5678    │◄──────│  port 3000 (SSE)   │  │
│  │               │ API   │                     │  │
│  │  bind mount:  │       │  env:               │  │
│  │  ./n8n-data/  │       │   N8N_API_URL       │  │
│  │               │       │   N8N_API_KEY       │  │
│  └──────┬───────┘       └─────────┬──────────┘  │
│         │ :5678                    │ :3000        │
└─────────┼─────────────────────────┼──────────────┘
          │                         │
     browser/webhooks         Claude Code (MCP)
```

- **n8n** (official `n8nio/n8n` image): Workflow engine, UI on port 5678, webhook receiver
- **n8n-mcp** (`ghcr.io/czlonkowski/n8n-mcp:latest`): MCP server exposing SSE on port 3000. Connects to n8n internally via `http://n8n:5678`
- **seed** (`curlimages/curl`): One-shot container that imports workflows from `workflows/` into n8n via REST API, then exits

## Services Detail

### n8n

- Image: `n8nio/n8n`
- Port: 5678 (UI + webhooks)
- Volume: `./n8n-data:/home/node/.n8n` (bind mount, git-ignored)
- Environment:
  - `N8N_HOST=0.0.0.0`
  - `N8N_PORT=5678`
  - `N8N_PROTOCOL=http`
  - `WEBHOOK_URL=http://localhost:5678/` (override with tunnel URL later for Telegram)
  - `GEMINI_API_KEY` (from `.env`)
  - `TELEGRAM_BOT_TOKEN` (from `.env`)

### n8n-mcp

- Image: `ghcr.io/czlonkowski/n8n-mcp:latest`
- Port: 3000 (SSE)
- Environment:
  - `N8N_API_URL=http://n8n:5678`
  - `N8N_API_KEY` (from `.env`)
  - `MCP_MODE=sse`
  - `WEBHOOK_SECURITY_MODE=moderate`
- Depends on: n8n

### seed

- Image: `curlimages/curl`
- Volumes: `./workflows:/workflows`, `./scripts:/scripts`
- Entrypoint: `sh /scripts/seed-workflows.sh`
- Environment:
  - `N8N_API_URL=http://n8n:5678`
  - `N8N_API_KEY` (from `.env`)
- Depends on: n8n
- One-shot: runs import script, then exits

## Workflow Sync

### Seeding (git -> n8n)

- `scripts/seed-workflows.sh` runs on every `docker-compose up`
- Uses n8n REST API (`POST /api/v1/workflows`) to import each `.json` from `workflows/`
- Idempotent: skips workflows that already exist (match by name or ID)
- All workflows imported as **inactive by default**
- `workflows/config.json` controls which workflows are activated on seed:

```json
{
  "gimli-v2.json": { "active": true },
  "telegram-run-agent.json": { "active": false }
}
```

- If a workflow is not listed in `config.json`, it stays inactive

### Exporting (n8n -> git)

- `scripts/export-workflow.sh` fetches a workflow by ID from the n8n API and writes it to `workflows/`
- Manual/intentional: only run when a workflow is in a commit-ready state
- Could be triggered by user, by Claude via MCP, or by a future automation

## Credential Handling

All secrets live in `.env` (git-ignored) and are passed to the n8n container as environment variables. Workflows reference them via `{{ $env.VAR_NAME }}` expressions instead of n8n's built-in credential system. This makes workflows portable and reproducible.

### .env.example (committed)

```
N8N_API_KEY=your-api-key-here
GEMINI_API_KEY=your-gemini-api-key-here
TELEGRAM_BOT_TOKEN=your-telegram-bot-token-here
```

### .env (git-ignored)

Actual secret values.

## Claude Code MCP Configuration

Claude Code connects to the n8n-mcp server over SSE at `http://localhost:3000`. No API keys needed in Claude Code config -- the MCP container already has them.

MCP settings entry:

```json
{
  "mcpServers": {
    "n8n-mcp": {
      "url": "http://localhost:3000"
    }
  }
}
```

## File Structure

New files added to the repo:

```
theCouncilOfElrond/
├── docker-compose.yml
├── .env.example
├── .env                        # git-ignored
├── scripts/
│   ├── seed-workflows.sh
│   └── export-workflow.sh
├── workflows/
│   ├── config.json
│   ├── gimli-v2.json           # existing
│   └── telegram-run-agent.json # existing
├── n8n-data/                   # git-ignored
└── .gitignore                  # updated
```

No custom Dockerfiles. All services use pre-built images.

## First-Time Setup Flow

1. `docker-compose up` -- n8n starts, MCP server starts (can't auth yet)
2. Open `localhost:5678`, create owner account, generate API key (Settings > API)
3. Put the API key + other secrets in `.env`
4. `docker-compose restart` -- seed script imports workflows, MCP server connects
5. Configure Claude Code MCP settings to point at `http://localhost:3000`

## Future Considerations

- **External access (Telegram webhooks):** Add a tunnel (ngrok, cloudflare tunnel) and update `WEBHOOK_URL` env var
- **Additional API keys:** Add to `.env.example` and `.env` as needed
- **Workflow export automation:** Could become an MCP tool or a git hook
- **n8n version pinning:** Currently uses `latest` tag; pin to a specific version for stability
