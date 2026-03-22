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

# --- Create or find credentials from env vars ---
# Returns the credential ID, creating the credential if it doesn't exist.
# Usage: ensure_credential "name" "type" '{"data":"fields"}'
ensure_credential() {
  cred_name="$1"
  cred_type="$2"
  cred_data="$3"

  # Check if credential already exists by name
  existing_cred_id=$(curl -sf -H "$AUTH_HEADER" "${API}/credentials" \
    | jq -r --arg name "$cred_name" '.data[] | select(.name == $name) | .id')

  if [ -n "$existing_cred_id" ]; then
    echo "$existing_cred_id"
    return
  fi

  # Create the credential
  result=$(echo "{\"name\":\"${cred_name}\",\"type\":\"${cred_type}\",\"data\":${cred_data}}" \
    | curl -sf -X POST \
      -H "$AUTH_HEADER" \
      -H "Content-Type: application/json" \
      -d @- \
      "${API}/credentials")
  echo "$result" | jq -r '.id'
}

# Telegram credential
TELEGRAM_CRED_ID=""
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ "$TELEGRAM_BOT_TOKEN" != "your-telegram-bot-token-here" ]; then
  echo "[seed] Setting up Telegram credential..."
  TELEGRAM_CRED_ID=$(ensure_credential "Telegram account" "telegramApi" \
    "{\"accessToken\":\"${TELEGRAM_BOT_TOKEN}\"}")
  echo "[seed] Telegram credential ready (id: $TELEGRAM_CRED_ID)"
fi

# Google Gemini credential
GEMINI_CRED_ID=""
if [ -n "$GEMINI_API_KEY" ] && [ "$GEMINI_API_KEY" != "your-gemini-api-key-here" ]; then
  echo "[seed] Setting up Gemini credential..."
  GEMINI_CRED_ID=$(ensure_credential "Google Gemini" "googlePalmApi" \
    "{\"apiKey\":\"${GEMINI_API_KEY}\",\"host\":\"https://generativelanguage.googleapis.com\"}")
  echo "[seed] Gemini credential ready (id: $GEMINI_CRED_ID)"
fi

# --- Fetch existing workflows, build name -> id map ---
existing=$(curl -sf -H "$AUTH_HEADER" "${API}/workflows?limit=100" | jq -r '.data[] | "\(.name)\t\(.id)"')

get_workflow_id_by_name() {
  echo "$existing" | awk -F'\t' -v name="$1" '$1 == name { print $2; exit }'
}

# --- Build jq filter to inject credentials into workflow nodes ---
# This patches node objects to add credential references based on node type.
build_credential_patch() {
  patch="."

  if [ -n "$TELEGRAM_CRED_ID" ]; then
    # Inject Telegram credentials into telegramTrigger and telegram nodes
    patch="${patch} | (.nodes[] |
      select(.type == \"n8n-nodes-base.telegramTrigger\" or .type == \"n8n-nodes-base.telegram\")) +=
      {\"credentials\": {\"telegramApi\": {\"id\": \"${TELEGRAM_CRED_ID}\", \"name\": \"Telegram account\"}}}"
  fi

  if [ -n "$GEMINI_CRED_ID" ]; then
    # Inject Gemini credentials into Google Gemini nodes
    patch="${patch} | (.nodes[] |
      select(.type == \"@n8n/n8n-nodes-langchain.googleGemini\")) +=
      {\"credentials\": {\"googlePalmApi\": {\"id\": \"${GEMINI_CRED_ID}\", \"name\": \"Google Gemini\"}}}"
  fi

  echo "$patch"
}

CRED_PATCH=$(build_credential_patch)

# --- Import each workflow JSON ---
for file in /workflows/*.json; do
  filename=$(basename "$file")

  # Skip config.json
  if [ "$filename" = "config.json" ]; then
    continue
  fi

  workflow_name=$(jq -r '.name' "$file")

  # Strip fields the API rejects, keep only what n8n accepts
  # Then inject credential references into matching nodes
  workflow_payload=$(jq "{
    name: .name,
    nodes: .nodes,
    connections: .connections,
    settings: (.settings | if . then {executionOrder: .executionOrder} else {} end)
  } | ${CRED_PATCH}" "$file")

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
