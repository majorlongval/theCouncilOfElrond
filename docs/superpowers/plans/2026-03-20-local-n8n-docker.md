# Local n8n + MCP Server Docker Setup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run n8n and the czlonkowski/n8n-mcp server locally in Docker, with workflow sync from git and Claude Code MCP access.

**Architecture:** docker-compose with three services (n8n, n8n-mcp, seed) on a shared network. Workflows seeded from `workflows/` on startup, exported back manually. GitHub API auth via `$env` header expressions; Telegram and Gemini credentials configured manually in n8n UI (these node types require n8n credential store entries — `$env` expressions don't work for built-in credential types).

**Spec deviation:** The spec states all credentials use `{{ $env.VAR_NAME }}`. This is only feasible for HTTP Request nodes (GitHub). Telegram and Gemini nodes require n8n's built-in credential system. The spec should be updated to reflect this. See Tasks 6-8 for the actual approach.

**Tech Stack:** Docker, docker-compose, n8n, czlonkowski/n8n-mcp, shell scripts, curl, jq

**Spec:** `docs/superpowers/specs/2026-03-20-local-n8n-docker-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `.gitignore` | Create | Ignore `n8n-data/`, `.env` |
| `.env.example` | Create | Template for required env vars |
| `docker-compose.yml` | Create | Define n8n, n8n-mcp, seed services |
| `scripts/seed-workflows.sh` | Create | Import workflows from `workflows/` into n8n via API |
| `scripts/export-workflow.sh` | Create | Export a workflow from n8n back to `workflows/` |
| `workflows/config.json` | Create | Controls which workflows are active after seeding |
| `workflows/gimli-v2.json` | Modify | Migrate credentials from Cloud IDs to `$env` / header auth |
| `workflows/telegram-run-agent.json` | Modify | Migrate credentials from Cloud IDs to `$env` / header auth |

---

### Task 1: .gitignore and .env.example

**Files:**
- Create: `.gitignore`
- Create: `.env.example`

- [ ] **Step 1: Create `.gitignore`**

```
n8n-data/
.env
```

- [ ] **Step 2: Create `.env.example`**

```
# n8n API key — generate in n8n UI: Settings > API > Create API Key
N8N_API_KEY=your-api-key-here

# Google Gemini API key — for Gimli agent
GEMINI_API_KEY=your-gemini-api-key-here

# Telegram bot token — from @BotFather
TELEGRAM_BOT_TOKEN=your-telegram-bot-token-here

# GitHub personal access token — for repo operations
GITHUB_TOKEN=your-github-token-here
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore .env.example
git commit -m "Add .gitignore and .env.example for Docker setup"
```

---

### Task 2: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  n8n:
    image: n8nio/n8n
    ports:
      - "5678:5678"
    volumes:
      - ./n8n-data:/home/node/.n8n
    env_file: .env
    environment:
      - N8N_PORT=5678
      - N8N_PROTOCOL=http
      - WEBHOOK_URL=http://localhost:5678/
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://localhost:5678/"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    networks:
      - council-net

  n8n-mcp:
    image: ghcr.io/czlonkowski/n8n-mcp:latest
    ports:
      - "3000:3000"
    env_file: .env
    environment:
      - N8N_API_URL=http://n8n:5678
      - WEBHOOK_SECURITY_MODE=moderate
    depends_on:
      n8n:
        condition: service_healthy
    networks:
      - council-net

  seed:
    image: alpine:3.19
    volumes:
      - ./workflows:/workflows:ro
      - ./scripts:/scripts:ro
    entrypoint: ["sh", "/scripts/seed-workflows.sh"]
    env_file: .env
    environment:
      - N8N_API_URL=http://n8n:5678
    depends_on:
      n8n:
        condition: service_healthy
    networks:
      - council-net

networks:
  council-net:
```

Notes:
- n8n healthcheck uses `wget` hitting the root URL (available in n8n image, `curl` may not be). The `/healthz` endpoint may not exist in all n8n versions, so we use `/` which returns 200 when the UI is ready.
- seed uses `alpine:3.19` instead of `curlimages/curl` because the seed script needs both `curl` and `jq`. The script installs them via `apk add`.
- `env_file: .env` passes all secrets to containers. On first run without `.env`, docker-compose will warn but still start n8n.

- [ ] **Step 2: Verify `docker-compose config` parses correctly**

Create a minimal `.env` for validation:
```bash
cp .env.example .env
docker compose config
```

Expected: valid YAML output with all three services, no errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "Add docker-compose with n8n, n8n-mcp, and seed services"
```

---

### Task 3: Seed script

**Files:**
- Create: `scripts/seed-workflows.sh`

The seed script is the most complex piece. It must:
1. Exit gracefully if no API key is set
2. Install curl + jq (alpine image)
3. List existing n8n workflows, build a name-to-ID map
4. For each `.json` in `/workflows/` (excluding `config.json`): upsert by name
5. Read `config.json` and activate marked workflows

- [ ] **Step 1: Create scripts directory and `scripts/seed-workflows.sh`**

```bash
mkdir -p scripts
```

```bash
#!/bin/sh
set -e

# --- Guard: skip if no API key ---
if [ -z "$N8N_API_KEY" ]; then
  echo "[seed] N8N_API_KEY not set — skipping workflow import."
  echo "[seed] Generate an API key in n8n UI (Settings > API), add it to .env, then run: docker compose up seed"
  exit 0
fi

# --- Install dependencies ---
apk add --no-cache curl jq > /dev/null 2>&1

API="${N8N_API_URL}/api/v1"
AUTH_HEADER="X-N8N-API-KEY: ${N8N_API_KEY}"

echo "[seed] Connected to n8n at ${N8N_API_URL}"

# --- Fetch existing workflows, build name -> id map ---
existing=$(curl -sf -H "$AUTH_HEADER" "${API}/workflows?limit=100" | jq -r '.data[] | "\(.name)\t\(.id)"')

get_workflow_id_by_name() {
  echo "$existing" | awk -F'\t' -v name="$1" '$1 == name { print $2; exit }'
}

# --- Import each workflow JSON ---
for file in /workflows/*.json; do
  filename=$(basename "$file")

  # Skip config.json
  if [ "$filename" = "config.json" ]; then
    continue
  fi

  workflow_name=$(jq -r '.name' "$file")

  # Force inactive on import
  workflow_payload=$(jq '.active = false' "$file")

  existing_id=$(get_workflow_id_by_name "$workflow_name")

  if [ -n "$existing_id" ]; then
    echo "[seed] Updating '$workflow_name' (id: $existing_id)"
    echo "$workflow_payload" | curl -sf -X PUT \
      -H "$AUTH_HEADER" \
      -H "Content-Type: application/json" \
      -d @- \
      "${API}/workflows/${existing_id}" > /dev/null
  else
    echo "[seed] Creating '$workflow_name'"
    result=$(echo "$workflow_payload" | curl -sf -X POST \
      -H "$AUTH_HEADER" \
      -H "Content-Type: application/json" \
      -d @- \
      "${API}/workflows")
    new_id=$(echo "$result" | jq -r '.id')
    # Append to existing map for subsequent lookups
    existing="${existing}
${workflow_name}	${new_id}"
  fi
done

# --- Activate workflows per config.json ---
if [ -f /workflows/config.json ]; then
  echo "[seed] Applying activation config..."
  jq -r 'to_entries[] | select(.value.active == true) | .key' /workflows/config.json | while read -r filename; do
    workflow_name=$(jq -r '.name' "/workflows/${filename}" 2>/dev/null) || continue
    wf_id=$(get_workflow_id_by_name "$workflow_name")
    if [ -n "$wf_id" ]; then
      echo "[seed] Activating '$workflow_name'"
      curl -sf -X PATCH \
        -H "$AUTH_HEADER" \
        -H "Content-Type: application/json" \
        -d '{"active": true}' \
        "${API}/workflows/${wf_id}" > /dev/null
    fi
  done
fi

echo "[seed] Done."
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/seed-workflows.sh
```

- [ ] **Step 3: Verify script syntax**

```bash
sh -n scripts/seed-workflows.sh
```

Expected: no output (no syntax errors).

- [ ] **Step 4: Commit**

```bash
git add scripts/seed-workflows.sh
git commit -m "Add seed script for importing workflows into n8n"
```

---

### Task 4: Export script

**Files:**
- Create: `scripts/export-workflow.sh`

- [ ] **Step 1: Create `scripts/export-workflow.sh`**

This script runs on the host (not in Docker), so it assumes `curl` and `jq` are available.

```bash
#!/bin/sh
set -e

# Usage: ./scripts/export-workflow.sh <workflow-name-or-id> [output-filename]
# Example: ./scripts/export-workflow.sh "Gimli — Builder Agent v2" gimli-v2.json

if [ -z "$1" ]; then
  echo "Usage: $0 <workflow-name-or-id> [output-filename]"
  echo ""
  echo "Examples:"
  echo "  $0 'Gimli — Builder Agent v2' gimli-v2.json"
  echo "  $0 123 my-workflow.json"
  exit 1
fi

# Load .env if it exists
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

N8N_API_URL="${N8N_API_URL:-http://localhost:5678}"
API="${N8N_API_URL}/api/v1"
AUTH_HEADER="X-N8N-API-KEY: ${N8N_API_KEY}"

if [ -z "$N8N_API_KEY" ]; then
  echo "Error: N8N_API_KEY not set. Add it to .env or export it."
  exit 1
fi

identifier="$1"
output_file="$2"

# Try to fetch by ID first (if identifier looks numeric)
case "$identifier" in
  [0-9]*)
    workflow=$(curl -sf -H "$AUTH_HEADER" "${API}/workflows/${identifier}" 2>/dev/null) || workflow=""
    ;;
esac

# If not found by ID, search by name
if [ -z "$workflow" ]; then
  all_workflows=$(curl -sf -H "$AUTH_HEADER" "${API}/workflows?limit=100")
  workflow_id=$(echo "$all_workflows" | jq -r --arg name "$identifier" '.data[] | select(.name == $name) | .id')

  if [ -z "$workflow_id" ]; then
    echo "Error: Workflow '$identifier' not found."
    exit 1
  fi

  workflow=$(curl -sf -H "$AUTH_HEADER" "${API}/workflows/${workflow_id}")
fi

# Strip volatile fields
cleaned=$(echo "$workflow" | jq 'del(.id, .active, .createdAt, .updatedAt, .versionId, .statistics, .meta, .tags, .shared, .homeProject, .usedCredentials)')

# Determine output filename
if [ -z "$output_file" ]; then
  # Derive from workflow name: lowercase, replace spaces/special chars with hyphens
  wf_name=$(echo "$cleaned" | jq -r '.name')
  output_file=$(echo "$wf_name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//').json
fi

output_path="workflows/${output_file}"
echo "$cleaned" | jq '.' > "$output_path"
echo "Exported to $output_path"
```

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/export-workflow.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/export-workflow.sh
git commit -m "Add export script for saving n8n workflows to git"
```

---

### Task 5: workflows/config.json

**Files:**
- Create: `workflows/config.json`

- [ ] **Step 1: Create `workflows/config.json`**

Start with everything inactive. User activates what they need.

```json
{
  "gimli-v2.json": { "active": false },
  "telegram-run-agent.json": { "active": false }
}
```

- [ ] **Step 2: Commit**

```bash
git add workflows/config.json
git commit -m "Add workflow activation config (all inactive by default)"
```

---

### Task 6: Migrate gimli-v2.json credentials

**Files:**
- Modify: `workflows/gimli-v2.json`

The Gimli workflow has these credential dependencies:
- **GitHub HTTP Request Tool nodes** (List Issues, Create Issue, Read File): use `predefinedCredentialType` with `githubOAuth2Api`. Migrate to header-based auth with `{{ $env.GITHUB_TOKEN }}`.
- **Telegram Trigger + Reply nodes**: no `credentials` block exists in this file (Cloud injected them at runtime). No action needed here — these nodes will show as misconfigured after import. User configures Telegram credentials in n8n UI on first setup (see Task 8).
- **Google Gemini node**: no `credentials` block exists in this file either. Same as Telegram — configure in n8n UI after import (see Task 8).

**Migration strategy for HTTP Request Tool nodes:**

For each of the three GitHub HTTP Request Tool nodes (`List Issues`, `Create Issue`, `Read File`):
- Remove `"authentication": "predefinedCredentialType"`
- Remove `"nodeCredentialType": "githubOAuth2Api"`
- Add/merge `"sendHeaders": true` and add `Authorization: token {{ $env.GITHUB_TOKEN }}` to `headerParameters`

- [ ] **Step 1: Migrate List Issues node**

In `workflows/gimli-v2.json`, the List Issues node (around line 89-100):

Change from:
```json
"authentication": "predefinedCredentialType",
"nodeCredentialType": "githubOAuth2Api",
"options": {}
```

To:
```json
"sendHeaders": true,
"headerParameters": {
  "parameters": [
    {
      "name": "Authorization",
      "value": "token {{ $env.GITHUB_TOKEN }}"
    }
  ]
},
"options": {}
```

- [ ] **Step 2: Migrate Create Issue node**

Same pattern. The Create Issue node (around line 103-118):

Change from:
```json
"authentication": "predefinedCredentialType",
"nodeCredentialType": "githubOAuth2Api",
"sendBody": true,
```

To:
```json
"sendHeaders": true,
"headerParameters": {
  "parameters": [
    {
      "name": "Authorization",
      "value": "token {{ $env.GITHUB_TOKEN }}"
    }
  ]
},
"sendBody": true,
```

- [ ] **Step 3: Migrate Read File node**

The Read File node (around line 121-141) already has `sendHeaders: true` with an Accept header. Add the Authorization header to the existing parameters array:

Change the `headerParameters` from:
```json
"headerParameters": {
  "parameters": [
    {
      "name": "Accept",
      "value": "application/vnd.github.raw+json"
    }
  ]
}
```

To:
```json
"headerParameters": {
  "parameters": [
    {
      "name": "Accept",
      "value": "application/vnd.github.raw+json"
    },
    {
      "name": "Authorization",
      "value": "token {{ $env.GITHUB_TOKEN }}"
    }
  ]
}
```

- [ ] **Step 4: Commit**

```bash
git add workflows/gimli-v2.json
git commit -m "Migrate gimli-v2 GitHub auth from Cloud credentials to env var headers"
```

---

### Task 7: Migrate telegram-run-agent.json credentials

**Files:**
- Modify: `workflows/telegram-run-agent.json`

This workflow has:
- **HTTP Request node** (GitHub dispatch, line 26-37): has explicit `credentials: { githubOAuth2Api: { id: "QWhuKjoUKqkvwQOj" } }`. Migrate to header auth.
- **Telegram Trigger** (line 44-55): has explicit `credentials: { telegramApi: { id: "sgMyhYXeaqFAi5kF" } }`. Remove Cloud credential IDs — user configures Telegram credentials in local n8n UI.
- **Send a text message** (line 88-103): same Telegram credential. Remove Cloud IDs.

- [ ] **Step 1: Migrate HTTP Request node to header auth**

Change the HTTP Request node to use header-based auth. Remove the `credentials` block and `predefinedCredentialType`/`nodeCredentialType` fields. Replace the existing empty header parameter with the Authorization header.

Remove from `parameters`:
```json
"authentication": "predefinedCredentialType",
"nodeCredentialType": "githubOAuth2Api",
```

Remove the `credentials` block at the node level (outside `parameters`):
```json
"credentials": {
  "githubOAuth2Api": {
    "id": "QWhuKjoUKqkvwQOj",
    "name": "GitHub account"
  }
}
```

Replace the existing `headerParameters` (which has an empty object `[{}]`) with:
```json
"headerParameters": {
  "parameters": [
    {
      "name": "Authorization",
      "value": "token {{ $env.GITHUB_TOKEN }}"
    }
  ]
}
```

Note: `sendHeaders` is already `true` in this node.

- [ ] **Step 2: Remove Cloud credential IDs from Telegram nodes**

Remove the `credentials` blocks from both the Telegram Trigger and Send a text message nodes. These reference Cloud-specific IDs that won't exist locally.

From Telegram Trigger, remove:
```json
"credentials": {
  "telegramApi": {
    "id": "sgMyhYXeaqFAi5kF",
    "name": "Telegram account"
  }
}
```

From Send a text message, remove the same `credentials` block.

**Important note:** After importing, these Telegram nodes will show as misconfigured in the n8n UI. The user must create a Telegram API credential in n8n (Settings > Credentials > Add > Telegram API) using their bot token, then assign it to these nodes. This is a one-time manual step. After that, re-export the workflow to capture the local credential references.

- [ ] **Step 3: Commit**

```bash
git add workflows/telegram-run-agent.json
git commit -m "Migrate telegram-run-agent credentials from Cloud IDs to local setup"
```

---

### Task 8: End-to-end verification

This task is manual. Run through the first-time setup flow and verify everything works.

- [ ] **Step 1: First boot (no .env)**

```bash
docker compose up
```

Expected:
- n8n starts and becomes healthy
- n8n-mcp starts (may log auth errors — expected, no API key yet)
- seed prints "N8N_API_KEY not set — skipping" and exits 0

- [ ] **Step 2: Create n8n account and API key**

1. Open `http://localhost:5678` in browser
2. Create owner account (email + password)
3. Go to Settings > API > Create API Key
4. Copy the key

- [ ] **Step 3: Configure .env**

```bash
cp .env.example .env
# Edit .env with real values:
# - N8N_API_KEY: the key from step 2
# - GEMINI_API_KEY: your Gemini key
# - TELEGRAM_BOT_TOKEN: your bot token
# - GITHUB_TOKEN: your GitHub PAT
```

- [ ] **Step 4: Run seed**

```bash
docker compose up seed
```

Expected:
- seed installs curl + jq
- Creates both workflows
- Prints "Done."

- [ ] **Step 5: Verify workflows in n8n UI**

1. Open `http://localhost:5678`
2. Go to Workflows
3. Verify both "Gimli — Builder Agent v2" and "Telegram Run Agent" appear
4. Both should be inactive (per config.json)

- [ ] **Step 6: Verify and configure MCP server**

```bash
docker compose restart n8n-mcp
```

Check that the n8n-mcp container starts without auth errors in logs:
```bash
docker compose logs n8n-mcp
```

Then add the MCP server to Claude Code's project settings (`.claude/settings.json`):
```json
{
  "mcpServers": {
    "n8n-mcp-local": {
      "url": "http://localhost:3000"
    }
  }
}
```

Verify Claude Code can connect by restarting Claude Code and checking MCP tool availability.

- [ ] **Step 7: Configure Telegram credentials (manual)**

1. In n8n UI: Settings > Credentials > Add Credential
2. Search "Telegram API", create with bot token
3. Open each workflow that uses Telegram nodes, assign the credential
4. Save workflows

- [ ] **Step 8: Configure Gemini credentials (manual)**

1. In n8n UI: Settings > Credentials > Add Credential
2. Search "Google Gemini" (or "Google PaLM"), create with API key
3. Open Gimli workflow, assign to the Gemini node
4. Save

- [ ] **Step 9: Export updated workflows back to git**

After configuring credentials in the UI, the workflow JSONs in n8n now have local credential references. Export them:

```bash
./scripts/export-workflow.sh "Gimli — Builder Agent v2" gimli-v2.json
./scripts/export-workflow.sh "Telegram Run Agent" telegram-run-agent.json
```

Review the diffs — they should only contain credential reference changes.

- [ ] **Step 10: Commit updated workflows**

```bash
git add workflows/
git commit -m "Update workflow JSONs with local n8n credential references"
```
