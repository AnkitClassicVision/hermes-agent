# OB_mybcat Agent Memory Provider V1 Implementation Plan

> **For Hermes:** Implement this plan directly with strict TDD: tests first, then provider code, then targeted verification.

**Goal:** Add a staging-safe Hermes external `MemoryProvider` adapter that connects Hermes to the OB_mybcat / Open Brain Agent Memory recall-writeback API.

**Architecture:** Implement a bundled memory plugin at `plugins/memory/ob_mybcat/`. The provider reads endpoint/key/scope config, recalls relevant Agent Memory context through `/recall`, and exposes explicit tools for recall/writeback/status. Writeback defaults to pending evidence, not instruction-grade memory, and blocks obvious secrets/PHI markers before sending content.

**Tech Stack:** Python stdlib (`urllib`, `json`, `threading`, `re`), Hermes `MemoryProvider`, pytest.

---

## Safety scope

- Staging-safe by default: no live config changes, no SQL migration, no Edge Function deploy.
- No secret fetching. The provider only reads already-present environment variables at runtime.
- Agent-written writebacks default to:
  - `review_status=pending`
  - `provenance=generated`
  - `can_use_as_instruction=false`
  - `can_use_as_evidence=true`
  - `requires_user_confirmation=true`
- No raw transcript auto-writeback. `sync_turn()` is a no-op unless `auto_writeback=true`, and v1 leaves it off by default.

## Files

- Create: `plugins/memory/ob_mybcat/__init__.py`
- Create: `plugins/memory/ob_mybcat/plugin.yaml`
- Create: `plugins/memory/ob_mybcat/README.md`
- Create: `tests/plugins/memory/test_ob_mybcat_provider.py`
- Keep untouched: SQL/RLS/deployment/config activation.

## Config contract

Environment variables:

- `OB_MYBCAT_AGENT_MEMORY_URL` or fallback `OB1_AGENT_MEMORY_ENDPOINT`
- `OB_MYBCAT_AGENT_MEMORY_KEY` or fallback `OB1_AGENT_MEMORY_KEY`
- Optional `OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID`
- Optional `OB_MYBCAT_AGENT_MEMORY_PROJECT_ID`
- Optional `OB_MYBCAT_AGENT_MEMORY_ENVIRONMENT`, default `staging`

Profile config file:

- `$HERMES_HOME/ob_mybcat_agent_memory.json`
- non-secret fields only: endpoint, workspace_id, project_id, environment, max_recall_results, include_unconfirmed, auto_recall, auto_writeback, mirror_builtin_writes, timeout.

## Task 1: Write provider tests first

**Objective:** Capture the v1 behavior before code exists.

**Test file:** `tests/plugins/memory/test_ob_mybcat_provider.py`

Test cases:

1. `is_available()` requires endpoint + key and does not make network calls.
2. Config save/load round-trips non-secret fields and env vars override profile config.
3. `prefetch()` posts a recall payload with schema version, query, workspace/project IDs, session/runtime metadata, and formats returned memories with review/use-policy labels.
4. Explicit `ob_mybcat_writeback` posts pending-evidence writeback payload with conservative use policy and source refs.
5. Writeback blocks obvious secret/PHI marker content before any HTTP call.
6. `sync_turn()` does not write raw transcripts by default.
7. `on_memory_write()` mirrors built-in memory writes only when `mirror_builtin_writes=true`.
8. `ob_mybcat_status` calls `/health` and redacts credentials from the response.

Verification:

```bash
python -m pytest tests/plugins/memory/test_ob_mybcat_provider.py -q -o 'addopts='
```

Expected before implementation: import failure / failing tests.

## Task 2: Implement the plugin

**Objective:** Add the bundled provider without activating it.

Implementation details:

- `ObMybcatAgentMemoryProvider(MemoryProvider)` with `name == "ob_mybcat"`.
- Thin `_AgentMemoryClient` using `urllib.request`.
- Tool schemas:
  - `ob_mybcat_recall`
  - `ob_mybcat_writeback`
  - `ob_mybcat_status`
- `prefetch()` uses `/recall` when `auto_recall=true` and returns fenced-friendly plain context. MemoryManager wraps it in `<memory-context>`.
- `handle_tool_call()` routes explicit tools.
- `sync_turn()` remains no-op unless a future compact-extraction path is explicitly enabled.
- `on_memory_write()` can mirror built-in memory writes as pending evidence only when configured.

## Task 3: Add provider metadata/docs

**Objective:** Make setup discoverable while keeping live activation manual.

- `plugin.yaml` describes provider and no pip dependencies.
- `README.md` explains staging setup, env vars, activation command, safety defaults, smoke-test checklist, and live gates.

## Task 4: Run targeted verification

Commands:

```bash
python -m pytest tests/plugins/memory/test_ob_mybcat_provider.py -q -o 'addopts='
python -m pytest tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py tests/run_agent/test_memory_sync_interrupted.py tests/plugins/memory/test_ob_mybcat_provider.py -q -o 'addopts='
```

Expected: all targeted tests pass.

## Task 5: Review diff and report

- `git diff --stat`
- `git diff -- plugins/memory/ob_mybcat tests/plugins/memory/test_ob_mybcat_provider.py plans/ob-mybcat-agent-memory-provider-v1-plan.md`
- Confirm no live config/deployment changes were made.
