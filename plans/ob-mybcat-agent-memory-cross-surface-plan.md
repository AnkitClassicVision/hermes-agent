# OB_mybcat Agent Memory Cross-Surface Bridges Implementation Plan

> **For Hermes:** Use TDD and keep this staging-safe. Do not live-enable production memory behavior.

**Goal:** Extend the OB_mybcat Agent Memory continuity pattern beyond Hermes' native `MemoryProvider` so Claude Code and Codex can receive the same governed work-memory context mechanically.

**Architecture:** Keep Hermes' provider as the canonical adapter/client. Add a small shared surface bridge module that initializes the provider, fetches a compact governed recall block, and prepends that block to Claude Code / Codex prompts. Add thin scripts so each work surface has an explicit, repeatable entrypoint without changing Claude Code or Codex internals.

**Surfaces in V1:**
- Hermes: existing `ob_mybcat` external `MemoryProvider`.
- Claude Code: wrapper that calls recall first, then invokes `claude -p` with a guarded context block prepended to the task.
- Codex: wrapper that calls recall first, then invokes `codex exec` with the same guarded context block prepended to the task.
- Generic/manual: context-only CLI for any other work surface.

**Non-goals:**
- No live OB_mybcat production enablement.
- No raw transcript writeback.
- No automatic writeback from Claude Code/Codex yet.
- No global shell alias installation yet.
- No direct secret fetching or credential persistence.

---

## Task 1: Add failing cross-surface tests

**Objective:** Specify the behavior for recall, prompt assembly, and Claude/Codex command construction before implementation.

**Files:**
- Create: `tests/plugins/memory/test_ob_mybcat_surface_bridge.py`

**Behaviors:**
1. `recall_context()` initializes the OB_mybcat provider with the requested surface (`claude_code`/`codex`) and includes workspace/project scope in the recall payload.
2. Prompt assembly fences OB_mybcat memory and explicitly says pending/generated memory is evidence only.
3. Claude command uses `claude -p <augmented_task>` and preserves pass-through args.
4. Codex command uses `codex exec <pass-through args> <augmented_task>`.
5. Dry-run execution prints JSON and never invokes the external agent binary.
6. `require_context=True` fails closed when recall returns no context.

**Verification:**
```bash
python -m pytest tests/plugins/memory/test_ob_mybcat_surface_bridge.py -q -o 'addopts='
```
Expected before implementation: fails because module does not exist.

---

## Task 2: Implement shared surface bridge module

**Objective:** Create reusable bridge functions and a CLI for recall and surface execution.

**Files:**
- Create: `plugins/memory/ob_mybcat/surface_bridge.py`

**Core functions:**
- `recall_context(query, surface, hermes_home=None, session_id=None)`
- `build_augmented_task(task, context, surface)`
- `build_surface_argv(surface, task, context, executable=None, passthrough_args=None)`
- `run_surface(surface, task, query=None, dry_run=False, require_context=False, ...)`
- `main(argv=None)`

**Safety rules:**
- Use existing provider activation requirements: HTTPS endpoint, env API key, workspace ID, project ID.
- Do not persist credentials.
- Do not print credential values in dry-run/status output.
- If unconfigured and `require_context=False`, proceed without context but report `context_injected=false` in dry-run.
- If unconfigured and `require_context=True`, fail before launching Claude/Codex.

---

## Task 3: Add thin scripts for work surfaces

**Objective:** Make the bridge usable without remembering the Python module path.

**Files:**
- Create: `scripts/ob-mybcat-agent-memory`
- Create: `scripts/ob-mybcat-claude`
- Create: `scripts/ob-mybcat-codex`

**Script behavior:**
- Resolve repo root relative to the script.
- Add repo root to `PYTHONPATH`.
- Exec `python3 -m plugins.memory.ob_mybcat.surface_bridge ...`.

**Usage examples:**
```bash
scripts/ob-mybcat-agent-memory recall "Classic Vision Care EHR"
scripts/ob-mybcat-claude --task "Implement the provider smoke test" -- --max-turns 10
scripts/ob-mybcat-codex --task "Review this diff" -- --full-auto
```

---

## Task 4: Document the mechanical difference and usage

**Objective:** Update the README so the distinction between repo context and governed work continuity is explicit.

**Files:**
- Modify: `plugins/memory/ob_mybcat/README.md`

**Docs must state:**
- Claude Code/Codex already read repo/project context.
- These wrappers add pre-task governed OB_mybcat work memory.
- This is staging-only until a real pilot proves value.
- Claude/Codex wrappers inject recall context only; they do not automatically write back.

---

## Task 5: Verify

**Commands:**
```bash
python -m pytest tests/plugins/memory/test_ob_mybcat_provider.py tests/plugins/memory/test_ob_mybcat_surface_bridge.py -q -o 'addopts='
python -m pytest tests/tools/test_memory_tool.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py tests/run_agent/test_memory_sync_interrupted.py tests/plugins/memory/test_ob_mybcat_provider.py tests/plugins/memory/test_ob_mybcat_surface_bridge.py -q -o 'addopts='
python -m py_compile plugins/memory/ob_mybcat/__init__.py plugins/memory/ob_mybcat/surface_bridge.py tests/plugins/memory/test_ob_mybcat_provider.py tests/plugins/memory/test_ob_mybcat_surface_bridge.py
```

**Report:** Explain that Hermes now has native provider integration, while Claude Code/Codex have explicit wrapper-based prompt injection. Emphasize this still does not live-enable production memory and does not prove product value until a pilot shows reduced re-explanation.
