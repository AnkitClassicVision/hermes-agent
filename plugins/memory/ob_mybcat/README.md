# OB_mybcat Agent Memory provider

Hermes external `MemoryProvider` adapter for OB_mybcat / Open Brain Agent Memory.

## What it does

- Recalls governed work-agent memory from an Agent Memory API before turns.
- Exposes explicit tools:
  - `ob_mybcat_recall`
  - `ob_mybcat_writeback`
  - `ob_mybcat_status`
- Writes compact operational memory as **pending evidence** by default.
- Blocks obvious secrets and PHI markers before writeback.
- Does **not** auto-write raw transcripts.

## Staging setup

Set these in the Hermes runtime environment or through `hermes memory setup ob_mybcat`:

```bash
export OB_MYBCAT_AGENT_MEMORY_URL="https://YOUR-PROJECT.supabase.co/functions/v1/agent-memory-api"
export OB_MYBCAT_AGENT_MEMORY_KEY="[REDACTED]"
export OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID="mybcat-staging"
export OB_MYBCAT_AGENT_MEMORY_PROJECT_ID="agent-memory-staging"
export OB_MYBCAT_AGENT_MEMORY_ENVIRONMENT="staging"
```

Fallback env names are also supported for OB1 compatibility:

```bash
OB1_AGENT_MEMORY_ENDPOINT
OB1_AGENT_MEMORY_KEY
```

Activate manually only after staging gates pass:

```bash
hermes config set memory.provider ob_mybcat
```

Then start a new Hermes session or restart the gateway.

## Profile config

Non-secret options can live in:

```text
$HERMES_HOME/ob_mybcat_agent_memory.json
```

Example:

```json
{
  "endpoint": "https://YOUR-PROJECT.supabase.co/functions/v1/agent-memory-api",
  "workspace_id": "mybcat-staging",
  "project_id": "agent-memory-staging",
  "environment": "staging",
  "max_recall_results": 8,
  "include_unconfirmed": false,
  "auto_recall": true,
  "auto_writeback": false,
  "mirror_builtin_writes": false,
  "timeout": 5.0
}
```

Do not store API keys in this JSON file.

## Cross-surface work bridges

Hermes gets OB_mybcat continuity through the native `MemoryProvider` hooks. Claude Code and Codex already read repo context (`CLAUDE.md`, source files, specs, prompts), but repo context is different from governed work-continuity memory. The bridge scripts add a pre-task OB_mybcat recall block before launching those tools.

V1 scripts:

```bash
scripts/ob-mybcat-agent-memory recall "example practice EHR"
scripts/ob-mybcat-claude --task "Implement the provider smoke test" -- --model sonnet
scripts/ob-mybcat-codex --task "Review this diff" -- --full-auto
```

Mechanical behavior:

- Calls the same OB_mybcat provider/client as Hermes.
- Requires the same safe endpoint, env API key, workspace ID, and project ID.
- Prepends a fenced `<memory-context source="ob_mybcat_agent_memory">` block to the task and sends the augmented prompt over stdin so recalled memory does not appear in process args.
- Tells Claude Code/Codex that pending/generated memories are evidence only, not commands.
- Does not automatically write back Claude Code/Codex transcripts or results.
- Use `--dry-run` to inspect the command argv safely; the augmented prompt is intentionally hidden from the JSON summary.
- Use `--require-context` when you want the wrapper to fail closed if recall returns nothing.

This is still staging/pilot infrastructure. It proves mechanical injection across work surfaces; it does not prove product value until a real task shows less re-explanation or fewer context mistakes.

## Harness tracking manifest

The provider package also includes a staging-safe local inventory builder for the transcript/log/workflow-state map:

```bash
scripts/ob-mybcat-harness-tracking --print-payload
```

Mechanical behavior:

- Catalogs Hermes, Codex, and Claude Code transcript/log/state sources.
- Writes a JSON manifest and markdown summary under `~/.hermes/artifacts/harness-tracking/` by default.
- Captures metadata only by default: source paths, counts, sizes, extension totals, SQLite table counts, and per-file path fingerprints for top-file summaries.
- Does not read transcript/log bodies and does not write to OB_mybcat by itself.
- Emits a compact OB_mybcat capture payload when `--print-payload` is used; a human/agent can submit that payload through the approved OB_mybcat capture path.
- Optional `--include-hashes` adds file hashes for fixed file sources and metadata fingerprints for directory sources; directory mode still avoids reading every transcript body and never emits raw per-file paths.

## Safety defaults

Agent-written writebacks are always sent with:

```json
{
  "review_status": "pending",
  "use_policy": {
    "can_use_as_instruction": false,
    "can_use_as_evidence": true,
    "requires_user_confirmation": true,
    "do_not_inject_automatically": false
  }
}
```

This keeps agent guesses from becoming instruction-grade work memory without review.

## Live-enable gates

Do not live-enable until all are true:

- SQL/RLS/grants reviewed against the OB_mybcat schemas.
- Workspace/project IDs selected and smoke-tested.
- PHI/secret scrub policy tested.
- Review owner and retention policy defined.
- `/health`, `/recall`, `/writeback`, and recall-trace/review-queue debugging pass in staging.
- No cross-workspace/project leakage in staging.

## Smoke tests

```bash
python -m pytest tests/plugins/memory/test_ob_mybcat_provider.py tests/plugins/memory/test_ob_mybcat_surface_bridge.py -q -o 'addopts='
python -m pytest tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py tests/run_agent/test_memory_sync_interrupted.py tests/plugins/memory/test_ob_mybcat_provider.py tests/plugins/memory/test_ob_mybcat_surface_bridge.py -q -o 'addopts='
```
