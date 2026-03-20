# Reactive Agents with n8n Orchestration

## Problem

The current Elrond-as-central-planner model has friction:
- Agents (especially Gimli) fail to close the review feedback loop
- Gimli is overloaded: building AND responding to reviews
- CI failures go unaddressed between cycles
- Hourly cron polling means slow reactions to events
- Adding new agents requires touching orchestration code

## Design

### Two-Layer Architecture

**n8n (orchestration + triggers):**
- Runs on n8n Cloud
- One workflow per agent — visual canvas shows the full organism
- Triggers: GitHub webhooks, Telegram bot, cron schedules
- Routes events to the right agent
- Workflow JSON committed to `workflows/` in the repo

**GitHub Actions (execution):**
- One parameterized workflow (or one per agent) triggered via `workflow_dispatch`
- Runs the existing Python executor with agent name + context as inputs
- Has full repo access — lint/test gates run against real code
- Results land on GitHub (PRs, comments, issues)

**Contract:**
```
n8n -> triggers GHA workflow_dispatch(agent_name, context_json)
GHA -> runs Python executor -> tools act on GitHub -> results visible on GitHub
n8n -> picks up results via GitHub webhooks (PR opened, comment posted, CI status)
```

### Agent Roster

| Agent | Role | Trigger | Scope |
|-------|------|---------|-------|
| Gimli | Builder | Issue labeled `ready` / Telegram `/run gimli` | create_pr, read_file, list_files, run_tests, run_lint |
| Legolas | PR Fixer | PR review posted / CI fails on open PR | push_to_pr, read_pr, read_file, run_tests, run_lint |
| Galadriel | Critic | PR opened / PR updated (new commits) | read_pr, post_comment, approve_pr, merge_pr |
| Gandalf | Scout | Cron (hourly) / Telegram `/run gandalf` | create_issue, read_file, list_files, write_memory |
| Samwise | Gardener | Cron (daily) / Telegram `/run samwise` | close_issue, close_pr, update_issue, list_issues, list_prs |
| Elrond | Tiebreaker | Agent requests coordination (future) | read-only, advisory |

### Reactive Triggers (not central planning)

Each agent has a clear trigger condition. No Elrond assignment needed for routine work:
- **Gimli** wakes when there's an issue to build
- **Legolas** wakes when a PR has feedback or failing CI
- **Galadriel** wakes when there's a PR to review
- **Gandalf** scouts on schedule
- **Samwise** tidies on schedule

Elrond's role shrinks to conflict resolution (two agents targeting same PR) and
strategic prioritization (Jord flags something via Telegram).

### Tool Gates (TDD + Lint enforcement)

`create_pr` and `push_to_pr` get a built-in gate:
1. Write files to a temp workspace locally
2. Run `ruff check` + `ruff format --check` on changed files
3. Run `pytest tests/brain/ -q` against the workspace
4. Only push to GitHub if both pass
5. Return error with lint/test output if they fail

This gate applies to both Gimli and Legolas — no agent can push broken code.

### Agent Toolkit (self-growth)

Creating a new agent requires:
1. An identity file: `agents/<name>.md` (personality, rules, deliverable)
2. A config entry in `config.yml` (name, role, tool scope)
3. An n8n workflow (can be cloned from a template workflow)

Existing agents can propose new agents via PR (write the identity file + config change).
The n8n workflow template makes it drag-and-drop to wire up triggers.

### Telegram Bot Commands

| Command | Action |
|---------|--------|
| `/run <agent>` | Manually trigger an agent |
| `/status` | Show open PRs, issues, CI status |
| `/pause` / `/resume` | Pause/resume automated triggers |

## Build Order

Incremental, one step at a time:

1. Get n8n running (n8n Cloud)
2. Build the simplest workflow: Telegram command triggers a GHA workflow
3. Add the Python executor (parameterized GHA workflow)
4. Wire up one agent end-to-end (Gimli or Legolas)
5. Add tool gates (lint/test before push)
6. Add remaining agents one by one
7. Add GitHub webhook triggers
8. Agent toolkit (template workflow)

## What Gets Carried Over from Foreman

- `brain/tools.py` — tool implementations (with new lint/test gates)
- `brain/executor.py` — LLM tool-use loop
- `brain/memory.py` — scoped memory with privacy
- `brain/config.py` — typed config loader
- `brain/llm_client.py` — LiteLLM wrapper
- `agents/*.md` — identity files (including new Legolas)
- `tests/` — test suite

## What Gets Replaced

- `brain/loop.py` -> n8n workflows handle scheduling and routing
- `brain/council.py` (Elrond orchestration) -> n8n trigger logic
- GHA cron trigger -> n8n triggers GHA via workflow_dispatch
