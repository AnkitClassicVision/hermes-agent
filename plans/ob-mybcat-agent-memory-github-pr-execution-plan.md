# OB_mybcat Agent Memory — GitHub PR execution plan

## Purpose

Ship the staging-safe OB_mybcat Agent Memory work through a clean, reviewable GitHub PR without mixing unrelated local work or enabling production memory behavior prematurely.

## Parent context

This work serves MyBCAT work-agent continuity across Hermes, Claude Code, and Codex. The intended outcome is a governed staging bridge, not live autonomous transcript ingestion.

## Scope for this PR

Include only the OB_mybcat Agent Memory and harness-tracking artifacts:

- `plans/ob-mybcat-agent-memory-provider-v1-plan.md`
- `plans/ob-mybcat-agent-memory-cross-surface-plan.md`
- `plans/ob-mybcat-agent-memory-staging-handoff.md`
- `plans/ob-mybcat-agent-memory-github-pr-execution-plan.md`
- `plugins/memory/ob_mybcat/README.md`
- `plugins/memory/ob_mybcat/__init__.py`
- `plugins/memory/ob_mybcat/harness_tracking.py`
- `plugins/memory/ob_mybcat/plugin.yaml`
- `plugins/memory/ob_mybcat/surface_bridge.py`
- `scripts/ob-mybcat-agent-memory`
- `scripts/ob-mybcat-claude`
- `scripts/ob-mybcat-codex`
- `scripts/ob-mybcat-harness-tracking`
- `tests/plugins/memory/test_ob_mybcat_provider.py`
- `tests/plugins/memory/test_ob_mybcat_surface_bridge.py`
- `tests/plugins/memory/test_ob_mybcat_harness_tracking.py`

Exclude unrelated current dirty work, especially `plans/founder-guided-autonomy-*` and any generated caches.

## Execution sequence

1. **Target repo gate**
   - Use Ankit-owned fork `AnkitClassicVision/hermes-agent` as the default GitHub target.
   - Do not open a public upstream PR to `NousResearch/hermes-agent` without explicit approval.

2. **Local validation gate**
   - Run the focused OB_mybcat memory and harness-tracking tests.
   - Run the broader memory-provider regression set.
   - Run compile/import smoke checks for the new plugin and CLI scripts.
   - Run wrapper dry-run smoke checks only with safe staging/demo inputs.

3. **Clean branch/worktree gate**
   - Create an isolated worktree from `fork/main` or the selected base.
   - Copy only the scoped files listed above.
   - Verify `git diff --name-status` contains no unrelated files.
   - Run `git diff --check` before commit.

4. **Commit and GitHub gate**
   - Commit with conventional message: `feat(memory): add OB_mybcat agent memory staging bridge`.
   - Push the branch to Ankit's fork.
   - Open a PR against `AnkitClassicVision/hermes-agent:main` unless explicitly retargeted.

5. **Pipeline gate**
   - Verify GitHub checks and Actions separately.
   - If there are no checks, report `no checks reported`; do not claim CI passed.
   - If checks fail, inspect logs, patch narrowly, rerun local tests, push, and re-check.

6. **Merge gate**
   - Merge only after local tests and GitHub checks are green, or after Ankit explicitly accepts a no-CI repo state.
   - Prefer squash merge and branch deletion.

7. **VPS/deployment gate**
   - Do not treat GitHub push or PR merge as a VPS deploy.
   - Confirm the runtime target and service owner before changing any VPS/control-plane state.
   - This PR should not live-enable `memory.provider = ob_mybcat`; production enablement requires the staging gates in `plans/ob-mybcat-agent-memory-staging-handoff.md`.

## Done state

- Clean PR exists in Ankit-owned GitHub repo.
- Scoped diff only.
- Local test commands and GitHub check status are recorded in the PR or final report.
- Merge/deploy status is explicitly separated from local tests and GitHub CI.
