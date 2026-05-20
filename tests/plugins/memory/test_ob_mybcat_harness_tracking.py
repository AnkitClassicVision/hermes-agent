import json
import sqlite3
from pathlib import Path

from plugins.memory.ob_mybcat.harness_tracking import (
    build_ob_capture_payload,
    build_tracking_manifest,
    write_tracking_artifacts,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sqlite_with_rows(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("create table threads(id text primary key, title text)")
    conn.execute("create table thread_spawn_edges(parent text, child text)")
    conn.execute("insert into threads values('thread-secret-id', 'Raw transcript title')")
    conn.execute("insert into thread_spawn_edges values('parent', 'child')")
    conn.commit()
    conn.close()


def test_manifest_catalogs_sources_without_raw_transcript_content(tmp_path):
    home = tmp_path
    _write(home / ".hermes/sessions/FAKE_PATIENT_RECORD_NAME.jsonl", "FAKE_PATIENT_RECORD_NAME phone 000-000-0000\n")
    _write(home / ".codex/sessions/2026/05/20/DUMMY_SECRET_MARKER.jsonl", "DUMMY_SECRET_MARKER=not-a-real-token\n")
    _write(home / ".claude/projects/my-project/Fake-client-raw-message-body.jsonl", "Fake client raw message body\n")

    manifest = build_tracking_manifest(home=home, include_hashes=False, top_files_limit=2)
    rendered = json.dumps(manifest, sort_keys=True)

    assert manifest["schema_version"] == "ob_mybcat_harness_tracking_manifest_v1"
    assert manifest["mode"] == "inventory_only"
    assert "FAKE_PATIENT_RECORD_NAME" not in rendered
    assert "DUMMY_SECRET_MARKER" not in rendered
    assert "Fake client raw message body" not in rendered
    assert str(tmp_path) not in rendered

    sources = {source["source_id"]: source for source in manifest["sources"]}
    assert sources["hermes_sessions"]["stats"]["file_count"] == 1
    assert sources["codex_sessions"]["stats"]["file_count"] == 1
    assert sources["claude_projects"]["stats"]["extension_counts"][".jsonl"] == 1
    assert "session_transcript_artifact" in sources["hermes_sessions"]["ob_mybcat_lanes"]
    assert sources["claude_projects"]["capture_policy"]["raw_content_default"] == "do_not_capture"


def test_sqlite_inspection_records_table_counts_without_rows(tmp_path):
    home = tmp_path
    _sqlite_with_rows(home / ".codex/state_5.sqlite")

    manifest = build_tracking_manifest(home=home, include_hashes=False)
    sources = {source["source_id"]: source for source in manifest["sources"]}
    sqlite_info = sources["codex_state_db"]["sqlite"]
    rendered = json.dumps(sqlite_info, sort_keys=True)

    assert sqlite_info["table_counts"]["threads"] == 1
    assert sqlite_info["table_counts"]["thread_spawn_edges"] == 1
    assert "thread-secret-id" not in rendered
    assert "Raw transcript title" not in rendered


def test_ob_capture_payload_is_compact_pending_evidence_and_sanitized(tmp_path):
    home = tmp_path
    _write(home / ".hermes/sessions/session_1.jsonl", "FAKE_PATIENT_RECORD_NAME phone 000-000-0000\n")
    _write(home / ".codex/log/codex-tui.log", "DUMMY_KEY_MARKER fake raw log line\n")

    manifest = build_tracking_manifest(home=home, include_hashes=False)
    payload = build_ob_capture_payload(manifest, artifact_path="/tmp/manifest.json")
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["type"] == "reference"
    assert payload["metadata"]["review_status"] == "pending_evidence"
    assert payload["metadata"]["capture_shape"] == "harness_tracking_manifest_v1"
    assert "Session transcript artifact" in payload["content"]
    assert "FAKE_PATIENT_RECORD_NAME" not in rendered
    assert "DUMMY_KEY_MARKER" not in rendered
    assert payload["metadata"]["artifact_path"] == "/tmp/manifest.json"


def test_write_tracking_artifacts_creates_manifest_and_summary(tmp_path):
    home = tmp_path / "home"
    _write(home / ".hermes/sessions/session_1.jsonl", "raw transcript text should not be copied\n")
    manifest = build_tracking_manifest(home=home, include_hashes=False)

    result = write_tracking_artifacts(manifest, tmp_path / "out")

    manifest_path = Path(result["manifest_path"])
    summary_path = Path(result["summary_path"])
    assert manifest_path.exists()
    assert summary_path.exists()
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["schema_version"] == "ob_mybcat_harness_tracking_manifest_v1"
    summary = summary_path.read_text(encoding="utf-8")
    assert "raw transcript text should not be copied" not in summary
    assert "OB_mybcat Harness Tracking Manifest" in summary
