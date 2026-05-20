"""Staging-safe harness tracking inventory for OB_mybcat continuity.

This module catalogs where Hermes, Codex, and Claude Code already store
session transcripts, workflow state, logs, and telemetry. It intentionally
collects metadata only by default: paths, counts, sizes, extension totals,
SQLite table counts, and OB_mybcat routing lanes. It does not read transcript
or log bodies into memory, and it never promotes transcript-derived content to
instruction-grade memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_VERSION = "ob_mybcat_harness_tracking_manifest_v1"
DEFAULT_TOP_FILES_LIMIT = 8


@dataclass(frozen=True)
class HarnessSourceDefinition:
    source_id: str
    relative_path: str
    source_type: str
    description: str
    ob_mybcat_lanes: tuple[str, ...]
    sensitivity_class: str
    retention_class: str
    raw_content_default: str = "do_not_capture"
    inspect_sqlite: bool = False
    proposed_capture: str = "catalog_pointer_and_safe_summary"
    notes: tuple[str, ...] = field(default_factory=tuple)


SOURCE_DEFINITIONS: tuple[HarnessSourceDefinition, ...] = (
    HarnessSourceDefinition(
        source_id="hermes_state_db",
        relative_path=".hermes/state.db",
        source_type="sqlite_state_db",
        description="Hermes session/message database with FTS, lineage, model, token/cost, and tool-call counters.",
        ob_mybcat_lanes=("source_catalog", "workflow_state", "tool_runtime_telemetry", "session_transcript_artifact"),
        sensitivity_class="restricted_transcript_metadata",
        retention_class="keep_active_index",
        inspect_sqlite=True,
        raw_content_default="metadata_only",
    ),
    HarnessSourceDefinition(
        source_id="hermes_sessions",
        relative_path=".hermes/sessions",
        source_type="session_transcript_dir",
        description="Hermes raw per-session JSON/JSONL transcript and request artifacts.",
        ob_mybcat_lanes=("source_catalog", "session_transcript_artifact", "work_ledger_checkpoint"),
        sensitivity_class="restricted_possible_phi_pii_secrets",
        retention_class="archive_high_value_summarize_rest",
        notes=("Do not ingest raw bodies by default.",),
    ),
    HarnessSourceDefinition(
        source_id="hermes_logs",
        relative_path=".hermes/logs",
        source_type="runtime_log_dir",
        description="Hermes agent, gateway, error, update, and curator logs.",
        ob_mybcat_lanes=("source_catalog", "tool_runtime_telemetry"),
        sensitivity_class="restricted_possible_secrets",
        retention_class="summarize_recent_archive_or_rotate",
    ),
    HarnessSourceDefinition(
        source_id="hermes_cron_output",
        relative_path=".hermes/cron/output",
        source_type="cron_output_dir",
        description="Markdown outputs from scheduled Hermes cron jobs.",
        ob_mybcat_lanes=("source_catalog", "workflow_state", "tool_runtime_telemetry"),
        sensitivity_class="restricted_possible_sensitive_work_content",
        retention_class="catalog_and_link_to_job_runs",
    ),
    HarnessSourceDefinition(
        source_id="hermes_kanban_db",
        relative_path=".hermes/kanban.db",
        source_type="sqlite_workflow_db",
        description="Hermes Kanban task, run, event, comment, dependency, notification, and autoroute state.",
        ob_mybcat_lanes=("source_catalog", "workflow_state", "work_ledger_checkpoint"),
        sensitivity_class="work_metadata",
        retention_class="keep_active_index",
        inspect_sqlite=True,
        raw_content_default="metadata_only",
    ),
    HarnessSourceDefinition(
        source_id="codex_sessions",
        relative_path=".codex/sessions",
        source_type="session_transcript_dir",
        description="Codex raw JSONL session transcripts organized by date.",
        ob_mybcat_lanes=("source_catalog", "session_transcript_artifact", "work_ledger_checkpoint"),
        sensitivity_class="restricted_possible_phi_pii_secrets",
        retention_class="archive_high_value_summarize_rest",
    ),
    HarnessSourceDefinition(
        source_id="codex_state_db",
        relative_path=".codex/state_5.sqlite",
        source_type="sqlite_state_db",
        description="Codex local thread, spawn-edge, dynamic-tool, job, and backfill state.",
        ob_mybcat_lanes=("source_catalog", "workflow_state"),
        sensitivity_class="restricted_transcript_metadata",
        retention_class="keep_active_index",
        inspect_sqlite=True,
        raw_content_default="metadata_only",
    ),
    HarnessSourceDefinition(
        source_id="codex_logs_db",
        relative_path=".codex/logs_2.sqlite",
        source_type="sqlite_log_db",
        description="Codex structured log database.",
        ob_mybcat_lanes=("source_catalog", "tool_runtime_telemetry"),
        sensitivity_class="restricted_possible_secrets",
        retention_class="summarize_recent_archive_or_rotate",
        inspect_sqlite=True,
        raw_content_default="metadata_only",
    ),
    HarnessSourceDefinition(
        source_id="codex_tui_log",
        relative_path=".codex/log/codex-tui.log",
        source_type="runtime_log_file",
        description="Codex TUI/debug log file.",
        ob_mybcat_lanes=("source_catalog", "tool_runtime_telemetry"),
        sensitivity_class="restricted_possible_secrets",
        retention_class="summarize_recent_then_rotate",
    ),
    HarnessSourceDefinition(
        source_id="codex_tmp",
        relative_path=".codex/tmp",
        source_type="temp_runtime_dir",
        description="Codex temporary sandbox/runtime artifacts.",
        ob_mybcat_lanes=("source_catalog",),
        sensitivity_class="runtime_temp",
        retention_class="delete_when_inactive_after_inventory",
        proposed_capture="count_size_only",
    ),
    HarnessSourceDefinition(
        source_id="claude_projects",
        relative_path=".claude/projects",
        source_type="session_transcript_dir",
        description="Claude Code project and subagent JSONL transcripts plus project-local artifacts.",
        ob_mybcat_lanes=("source_catalog", "session_transcript_artifact", "work_ledger_checkpoint"),
        sensitivity_class="restricted_possible_phi_pii_secrets",
        retention_class="archive_high_value_summarize_rest",
    ),
    HarnessSourceDefinition(
        source_id="claude_telemetry",
        relative_path=".claude/telemetry",
        source_type="failed_telemetry_dir",
        description="Claude Code failed telemetry event dumps.",
        ob_mybcat_lanes=("source_catalog", "tool_runtime_telemetry"),
        sensitivity_class="restricted_possible_sensitive_events",
        retention_class="summarize_error_categories_then_delete_or_archive",
    ),
    HarnessSourceDefinition(
        source_id="claude_computer_use",
        relative_path=".claude/computer-use-data",
        source_type="browser_state_dir",
        description="Claude computer-use browser profile/state.",
        ob_mybcat_lanes=("source_catalog", "governance_review_queue"),
        sensitivity_class="hard_restricted_browser_state",
        retention_class="inventory_only_do_not_ingest",
        proposed_capture="inventory_only",
        notes=("May contain cookies, browsing history, local storage, or credentials; never ingest raw files.",),
    ),
)


LANE_LABELS: dict[str, str] = {
    "source_catalog": "Source catalog",
    "session_transcript_artifact": "Session transcript artifact",
    "work_ledger_checkpoint": "Work Ledger checkpoint",
    "agent_memory_evidence": "Agent Memory evidence",
    "workflow_state": "Workflow state",
    "tool_runtime_telemetry": "Tool/runtime telemetry",
    "github_pipeline_state": "GitHub / PR / pipeline state",
    "governance_review_queue": "Governance / review queue",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fmt_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def _redact_path(path: Path, home: Path) -> str:
    try:
        rel = path.resolve().relative_to(home.resolve())
        rel_text = str(rel).replace("\\", "/")
        return f"~/{rel_text}" if rel_text else "~"
    except Exception:
        return "[outside-home]"


def _safe_stat(path: Path) -> tuple[int, float] | None:
    try:
        stat = path.stat()
        return stat.st_size, stat.st_mtime
    except OSError:
        return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extension(path: Path) -> str:
    return path.suffix or "<none>"


def _sorted_extension_counts(extension_counts: dict[str, int]) -> dict[str, int]:
    return dict(sorted(extension_counts.items(), key=lambda item: (-item[1], item[0])))


def _top_file_entries(entries: list[tuple[int, float, Path]], home: Path, limit: int) -> list[dict[str, Any]]:
    top = sorted(entries, key=lambda item: (item[0], item[1]), reverse=True)[: max(0, limit)]
    results: list[dict[str, Any]] = []
    for size, mtime, path in top:
        try:
            rel = str(path.resolve().relative_to(home.resolve())).replace("\\", "/")
        except Exception:
            rel = path.name
        results.append(
            {
                "path_fingerprint_sha256": hashlib.sha256(rel.encode("utf-8", errors="ignore")).hexdigest(),
                "extension": _extension(path),
                "bytes": size,
                "size": _fmt_size(size),
                "mtime": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
            }
        )
    return results


def _directory_stats(path: Path, home: Path, *, top_files_limit: int, include_hashes: bool) -> dict[str, Any]:
    file_count = 0
    total_bytes = 0
    latest_mtime = 0.0
    extension_counts: dict[str, int] = {}
    top_candidates: list[tuple[int, float, Path]] = []
    digest = hashlib.sha256() if include_hashes else None

    for child in path.rglob("*"):
        if not child.is_file():
            continue
        stat = _safe_stat(child)
        if stat is None:
            continue
        size, mtime = stat
        file_count += 1
        total_bytes += size
        latest_mtime = max(latest_mtime, mtime)
        extension_counts[_extension(child)] = extension_counts.get(_extension(child), 0) + 1
        top_candidates.append((size, mtime, child))
        if digest is not None:
            try:
                rel = str(child.resolve().relative_to(home.resolve())).replace("\\", "/")
            except Exception:
                rel = child.name
            digest.update(rel.encode("utf-8", errors="ignore"))
            digest.update(str(size).encode("ascii"))
            digest.update(str(int(mtime)).encode("ascii"))

    stats: dict[str, Any] = {
        "kind": "directory",
        "exists": True,
        "path": _redact_path(path, home),
        "file_count": file_count,
        "bytes": total_bytes,
        "size": _fmt_size(total_bytes),
        "latest_mtime": datetime.fromtimestamp(latest_mtime, timezone.utc).isoformat() if latest_mtime else None,
        "extension_counts": _sorted_extension_counts(extension_counts),
        "top_files": _top_file_entries(top_candidates, home, top_files_limit),
    }
    if digest is not None:
        stats["tree_fingerprint_sha256"] = digest.hexdigest()
        stats["hash_mode"] = "metadata_fingerprint_only_no_file_bodies"
    return stats


def _file_stats(path: Path, home: Path, *, include_hashes: bool) -> dict[str, Any]:
    stat = _safe_stat(path)
    if stat is None:
        return {"kind": "file", "exists": False, "path": _redact_path(path, home)}
    size, mtime = stat
    stats: dict[str, Any] = {
        "kind": "file",
        "exists": True,
        "path": _redact_path(path, home),
        "file_count": 1,
        "bytes": size,
        "size": _fmt_size(size),
        "mtime": datetime.fromtimestamp(mtime, timezone.utc).isoformat(),
        "extension_counts": {_extension(path): 1},
    }
    if include_hashes:
        stats["sha256"] = _sha256_file(path)
        stats["hash_mode"] = "full_file_sha256"
    return stats


def _missing_stats(path: Path, home: Path) -> dict[str, Any]:
    return {"kind": "missing", "exists": False, "path": _redact_path(path, home)}


def _source_stats(path: Path, home: Path, *, top_files_limit: int, include_hashes: bool) -> dict[str, Any]:
    if not path.exists():
        return _missing_stats(path, home)
    if path.is_dir():
        return _directory_stats(path, home, top_files_limit=top_files_limit, include_hashes=include_hashes)
    if path.is_file():
        return _file_stats(path, home, include_hashes=include_hashes)
    return {"kind": "other", "exists": True, "path": _redact_path(path, home)}


def _inspect_sqlite(path: Path, *, max_tables: int = 60) -> dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {"available": False, "reason": "not_found"}
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0)
        rows = conn.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"
        ).fetchall()
        tables = [str(row[0]) for row in rows][:max_tables]
        counts: dict[str, int | str] = {}
        for table in tables:
            try:
                quoted = table.replace('"', '""')
                counts[table] = int(conn.execute(f'select count(*) from "{quoted}"').fetchone()[0])
            except Exception as exc:  # pragma: no cover - rare schema-specific failures
                counts[table] = f"unavailable:{type(exc).__name__}"
        conn.close()
        return {"available": True, "tables": tables, "table_counts": counts, "row_values_read": False}
    except Exception as exc:
        return {"available": False, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _policy_for(definition: HarnessSourceDefinition) -> dict[str, Any]:
    return {
        "raw_content_default": definition.raw_content_default,
        "proposed_capture": definition.proposed_capture,
        "review_status_default": "pending_evidence",
        "can_use_as_instruction_default": False,
        "requires_scrub_before_content_ingest": True,
    }


def _source_entry(
    definition: HarnessSourceDefinition,
    home: Path,
    *,
    top_files_limit: int,
    include_hashes: bool,
    inspect_sqlite: bool,
) -> dict[str, Any]:
    path = home / definition.relative_path
    entry: dict[str, Any] = {
        "source_id": definition.source_id,
        "source_type": definition.source_type,
        "description": definition.description,
        "path": _redact_path(path, home),
        "ob_mybcat_lanes": list(definition.ob_mybcat_lanes),
        "sensitivity_class": definition.sensitivity_class,
        "retention_class": definition.retention_class,
        "capture_policy": _policy_for(definition),
        "stats": _source_stats(path, home, top_files_limit=top_files_limit, include_hashes=include_hashes),
    }
    if definition.notes:
        entry["notes"] = list(definition.notes)
    if inspect_sqlite and definition.inspect_sqlite:
        entry["sqlite"] = _inspect_sqlite(path)
    return entry


def _lane_rollup(sources: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rollup: dict[str, dict[str, Any]] = {}
    for source in sources:
        for lane in source.get("ob_mybcat_lanes", []):
            item = rollup.setdefault(lane, {"label": LANE_LABELS.get(lane, lane), "sources": [], "existing_sources": 0})
            item["sources"].append(source["source_id"])
            if source.get("stats", {}).get("exists"):
                item["existing_sources"] += 1
    return rollup


def build_tracking_manifest(
    *,
    home: str | Path | None = None,
    include_hashes: bool = False,
    top_files_limit: int = DEFAULT_TOP_FILES_LIMIT,
    inspect_sqlite: bool = True,
) -> dict[str, Any]:
    """Build a safe current-state manifest for harness tracking sources.

    The manifest is inventory-only: it does not include raw transcript/log rows.
    If ``include_hashes`` is true, individual files get full SHA256 only for
    file sources; directory sources get a metadata fingerprint rather than
    reading every file body.
    """
    root = Path(home).expanduser() if home is not None else Path.home()
    root = root.resolve()
    sources = [
        _source_entry(
            definition,
            root,
            top_files_limit=top_files_limit,
            include_hashes=include_hashes,
            inspect_sqlite=inspect_sqlite,
        )
        for definition in SOURCE_DEFINITIONS
    ]
    existing = [source for source in sources if source.get("stats", {}).get("exists")]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_iso(),
        "mode": "inventory_only",
        "home": "~",
        "source_count": len(sources),
        "existing_source_count": len(existing),
        "include_hashes": include_hashes,
        "raw_content_included": False,
        "safety_policy": {
            "raw_transcript_default": "do_not_capture",
            "transcript_chunks_default": "redacted_evidence_only",
            "agent_memory_default_review_status": "pending_evidence",
            "instruction_grade_requires_review": True,
            "phi_secret_scrub_required_before_content_ingest": True,
        },
        "lane_rollup": _lane_rollup(sources),
        "sources": sources,
    }


def _source_line(source: dict[str, Any]) -> str:
    stats = source.get("stats", {})
    exists = "yes" if stats.get("exists") else "no"
    size = stats.get("size") or "0 B"
    count = stats.get("file_count")
    count_text = f", files={count}" if count is not None else ""
    return f"- {source['source_id']}: exists={exists}, size={size}{count_text}, lanes={', '.join(source.get('ob_mybcat_lanes', []))}"


def build_ob_capture_payload(manifest: dict[str, Any], *, artifact_path: str | None = None) -> dict[str, Any]:
    """Return a compact OB_mybcat capture payload for this manifest."""
    existing = [source for source in manifest.get("sources", []) if source.get("stats", {}).get("exists")]
    lines = [
        "OB_mybcat harness tracking implementation checkpoint.",
        "",
        "Session transcript artifact lane is included: raw transcripts remain source evidence; OB_mybcat should store pointers, hashes/fingerprints, safe summaries, and reviewed extracted facts rather than unredacted raw transcript bodies.",
        "",
        f"Manifest schema: {manifest.get('schema_version')}",
        f"Generated: {manifest.get('generated_at')}",
        f"Sources configured: {manifest.get('source_count')} total, {manifest.get('existing_source_count')} present.",
        f"Raw content included: {manifest.get('raw_content_included')}",
        "",
        "Existing sources:",
    ]
    lines.extend(_source_line(source) for source in existing[:20])
    if len(existing) > 20:
        lines.append(f"- ... {len(existing) - 20} more existing sources omitted from capture summary")
    lines.extend(
        [
            "",
            "Safety defaults: review_status=pending_evidence; can_use_as_instruction=false; PHI/secret scrub required before any transcript or log content ingestion.",
        ]
    )
    metadata = {
        "capture_shape": "harness_tracking_manifest_v1",
        "scope": "work",
        "review_status": "pending_evidence",
        "raw_content_included": False,
        "source_count": manifest.get("source_count"),
        "existing_source_count": manifest.get("existing_source_count"),
        "topics": [
            "agent-memory",
            "session-transcripts",
            "harness-tracking",
            "ob-mybcat",
            "work-ledger",
            "cross-surface-continuity",
        ],
    }
    if artifact_path:
        metadata["artifact_path"] = artifact_path
    return {"type": "reference", "content": "\n".join(lines), "metadata": metadata}


def _manifest_basename() -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    return f"ob-mybcat-harness-tracking-manifest-{stamp}"


def _markdown_summary(manifest: dict[str, Any], *, manifest_path: str | None = None) -> str:
    lines = [
        "# OB_mybcat Harness Tracking Manifest",
        "",
        f"Generated: {manifest.get('generated_at')}",
        f"Schema: `{manifest.get('schema_version')}`",
        f"Mode: `{manifest.get('mode')}`",
        f"Raw content included: `{manifest.get('raw_content_included')}`",
        "",
        "## Safety policy",
        "",
    ]
    for key, value in manifest.get("safety_policy", {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Lane rollup", ""])
    for lane, info in sorted(manifest.get("lane_rollup", {}).items()):
        lines.append(
            f"- {info.get('label', lane)}: {info.get('existing_sources', 0)} existing source(s); "
            f"sources={', '.join(info.get('sources', []))}"
        )
    lines.extend(["", "## Sources", ""])
    lines.extend(_source_line(source) for source in manifest.get("sources", []))
    if manifest_path:
        lines.extend(["", f"Full JSON manifest: `{manifest_path}`"])
    lines.extend(
        [
            "",
            "## Policy note",
            "",
            "This summary intentionally excludes raw transcript/log bodies. Transcript and log content must be scrubbed and reviewed before any semantic chunking or Agent Memory promotion.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_tracking_artifacts(manifest: dict[str, Any], out_dir: str | Path) -> dict[str, str]:
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    base = _manifest_basename()
    manifest_path = out / f"{base}.json"
    summary_path = out / f"{base}.md"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    summary_path.write_text(
        _markdown_summary(manifest, manifest_path=str(manifest_path)),
        encoding="utf-8",
    )
    return {"manifest_path": str(manifest_path), "summary_path": str(summary_path)}


def _default_out_dir() -> Path:
    return Path.home() / ".hermes" / "artifacts" / "harness-tracking"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a staging-safe OB_mybcat harness tracking manifest.")
    parser.add_argument("--home", default=str(Path.home()), help="Home directory to inventory. Defaults to current user's home.")
    parser.add_argument("--out-dir", default=str(_default_out_dir()), help="Directory for JSON/markdown artifacts.")
    parser.add_argument("--include-hashes", action="store_true", help="Add file SHA256 for file sources and metadata fingerprints for directories.")
    parser.add_argument("--top-files-limit", type=int, default=DEFAULT_TOP_FILES_LIMIT, help="Maximum top-sized files to list per source.")
    parser.add_argument("--no-sqlite", action="store_true", help="Skip SQLite table/count inspection.")
    parser.add_argument("--print-payload", action="store_true", help="Print compact OB_mybcat capture payload JSON after writing artifacts.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    manifest = build_tracking_manifest(
        home=args.home,
        include_hashes=bool(args.include_hashes),
        top_files_limit=max(0, int(args.top_files_limit)),
        inspect_sqlite=not args.no_sqlite,
    )
    result = write_tracking_artifacts(manifest, args.out_dir)
    if args.print_payload:
        payload = build_ob_capture_payload(manifest, artifact_path=result["manifest_path"])
        print(json.dumps({"artifacts": result, "ob_capture_payload": payload}, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
