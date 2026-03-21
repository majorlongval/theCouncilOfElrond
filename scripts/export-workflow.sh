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
