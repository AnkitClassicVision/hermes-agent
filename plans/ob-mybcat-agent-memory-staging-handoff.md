# OB_mybcat Agent Memory — staging handoff

## Current state

This repo now has a staging-safe OB_mybcat Agent Memory bridge across the three intended work surfaces:

1. **Hermes** — native external `MemoryProvider` plugin: `plugins/memory/ob_mybcat/`.
2. **Claude Code** — wrapper script: `scripts/ob-mybcat-claude`.
3. **Codex** — wrapper script: `scripts/ob-mybcat-codex`.

The shared CLI/context builder is `plugins/memory/ob_mybcat/surface_bridge.py`; the general command is `scripts/ob-mybcat-agent-memory`.

## Safety posture

Not live-enabled yet.

The implementation is intentionally staging-safe:

- Requires a safe HTTPS endpoint.
- Requires API key from environment only; no keys are written to config JSON.
- Requires `workspace_id` and `project_id` so recall/writeback is scoped.
- Only supports the `staging` environment choice in setup/config; `live`, `prod`, `production`, and other non-staging labels fail closed even if an allow-live env var is present.
- Blocks obvious secret/PHI-like content before outbound recall/writeback.
- Redacts or omits restricted recalled content before rendering context.
- Defaults all agent writebacks to `review_status: pending` and evidence-only use policy.
- Tool-originated writebacks cannot claim trusted `observed` or `user_confirmed` provenance.
- Does not auto-write raw transcripts.
- Claude/Codex wrapper prompts are sent over stdin, not argv, so recalled memory is not exposed in process listings or dry-run JSON.
- Dry-run summaries hide the augmented prompt.

## Files added

- `plans/ob-mybcat-agent-memory-provider-v1-plan.md`
- `plans/ob-mybcat-agent-memory-cross-surface-plan.md`
- `plans/ob-mybcat-agent-memory-staging-handoff.md`
- `plugins/memory/ob_mybcat/__init__.py`
- `plugins/memory/ob_mybcat/plugin.yaml`
- `plugins/memory/ob_mybcat/README.md`
- `plugins/memory/ob_mybcat/surface_bridge.py`
- `plugins/memory/ob_mybcat/harness_tracking.py`
- `scripts/ob-mybcat-agent-memory`
- `scripts/ob-mybcat-claude`
- `scripts/ob-mybcat-codex`
- `scripts/ob-mybcat-harness-tracking`
- `tests/plugins/memory/test_ob_mybcat_provider.py`
- `tests/plugins/memory/test_ob_mybcat_surface_bridge.py`
- `tests/plugins/memory/test_ob_mybcat_harness_tracking.py`

## Verification commands run

```bash
python -m pytest tests/plugins/memory/test_ob_mybcat_provider.py tests/plugins/memory/test_ob_mybcat_surface_bridge.py tests/plugins/memory/test_ob_mybcat_harness_tracking.py -q -o 'addopts='
# 33 passed

python -m pytest tests/tools/test_memory_tool.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py tests/run_agent/test_memory_sync_interrupted.py tests/plugins/memory/test_ob_mybcat_provider.py tests/plugins/memory/test_ob_mybcat_surface_bridge.py tests/plugins/memory/test_ob_mybcat_harness_tracking.py -q -o 'addopts='
# 145 passed

python -m pytest tests/plugins/memory -q -o 'addopts='
# 194 passed

python -m py_compile plugins/memory/ob_mybcat/__init__.py plugins/memory/ob_mybcat/surface_bridge.py plugins/memory/ob_mybcat/harness_tracking.py tests/plugins/memory/test_ob_mybcat_provider.py tests/plugins/memory/test_ob_mybcat_surface_bridge.py tests/plugins/memory/test_ob_mybcat_harness_tracking.py
# passed
```

Dry-run wrapper smoke checks also passed:

```bash
scripts/ob-mybcat-agent-memory recall "safe staging query"
scripts/ob-mybcat-claude --task "Dry run smoke" --dry-run -- --model sonnet
scripts/ob-mybcat-codex --task "Dry run smoke" --dry-run -- --full-auto
```

## Staging environment variables

Values are intentionally not recorded here.

```bash
export OB_MYBCAT_AGENT_MEMORY_URL="https://.../agent-memory-api"
export OB_MYBCAT_AGENT_MEMORY_KEY="[REDACTED]"
export OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID="mybcat-staging"
export OB_MYBCAT_AGENT_MEMORY_PROJECT_ID="agent-memory-staging"
export OB_MYBCAT_AGENT_MEMORY_ENVIRONMENT="staging"
```

Fallback compatibility:

```bash
OB1_AGENT_MEMORY_ENDPOINT
OB1_AGENT_MEMORY_KEY
```

## How to use in staging

Hermes native provider, after env/scope are set and live gates pass:

```bash
hermes config set memory.provider ob_mybcat
# Then restart gateway or start a fresh Hermes session.
```

Claude Code wrapper:

```bash
scripts/ob-mybcat-claude --task "Implement the next provider test" -- --model sonnet
```

Codex wrapper:

```bash
scripts/ob-mybcat-codex --task "Review this diff" -- --full-auto
```

Recall only:

```bash
scripts/ob-mybcat-agent-memory recall "example practice EHR" --surface claude_code
```

Require fail-closed recall:

```bash
scripts/ob-mybcat-codex --task "Do the task" --require-context -- --full-auto
```

## Live-enable gates

Do not enable for production work until these pass:

1. Agent Memory API endpoint is deployed in staging and reviewed.
2. SQL/RLS/grants are reviewed against OB_mybcat schemas.
3. Workspace/project IDs are final and smoke-tested.
4. PHI/secret scrub policy passes staging tests.
5. Review queue owner and retention policy are defined.
6. `/health`, `/recall`, `/writeback`, and recall trace/debug views pass smoke tests.
7. No cross-workspace/project leakage in staging.
8. A real pilot task proves reduced context re-explanation or fewer context mistakes.

## Repo caveats

At PR prep time, these OB_mybcat Agent Memory files were moved into a clean worktree/branch based on latest `fork/main`. Keep unrelated local changes from the original checkout separate, including founder-guided-autonomy plan/spec files.

Hermes config currently has `agent.max_turns = 1000` as a temporary project setting. Revert to the preferred complex-task baseline later if desired.
