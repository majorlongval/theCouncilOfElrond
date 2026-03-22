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

  # Strip fields the API rejects (read-only, extra properties)
  # Keep only: name, nodes, connections, settings (cleaned)
  workflow_payload=$(jq '{
    name: .name,
    nodes: .nodes,
    connections: .connections,
    settings: (.settings | if . then {executionOrder: .executionOrder} else {} end)
  }' "$file")

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
