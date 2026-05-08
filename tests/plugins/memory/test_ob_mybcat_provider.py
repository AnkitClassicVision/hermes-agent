import json

import pytest

from plugins.memory import load_memory_provider
from plugins.memory.ob_mybcat import (
    ObMybcatAgentMemoryProvider,
    _clean_text,
    _load_ob_mybcat_config,
    _save_ob_mybcat_config,
)


_OB_MYBCAT_ENV_VARS = [
    "OB_MYBCAT_AGENT_MEMORY_URL",
    "OB1_AGENT_MEMORY_ENDPOINT",
    "OB_MYBCAT_AGENT_MEMORY_KEY",
    "OB1_AGENT_MEMORY_KEY",
    "OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID",
    "OB_MYBCAT_AGENT_MEMORY_PROJECT_ID",
    "OB_MYBCAT_AGENT_MEMORY_ENVIRONMENT",
    "OB_MYBCAT_AGENT_MEMORY_ALLOW_LIVE",
]


@pytest.fixture(autouse=True)
def clear_ob_mybcat_env(monkeypatch):
    for var in _OB_MYBCAT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


class FakeAgentMemoryClient:
    def __init__(self):
        self.endpoint = ""
        self.api_key = ""
        self.timeout = None
        self.posts = []
        self.gets = []
        self.post_responses = {}
        self.get_responses = {}

    def configure(self, *, endpoint, api_key, timeout):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout
        return self

    def post(self, path, payload):
        self.posts.append({"path": path, "payload": payload})
        return self.post_responses.get(path, {})

    def get(self, path):
        self.gets.append(path)
        return self.get_responses.get(path, {})


@pytest.fixture
def provider_with_client(monkeypatch, tmp_path):
    fake = FakeAgentMemoryClient()
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_URL", "https://example.test/functions/v1/agent-memory-api")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_KEY", "test-secret-key")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_PROJECT_ID", "project-1")

    def factory(*, endpoint, api_key, timeout):
        return fake.configure(endpoint=endpoint, api_key=api_key, timeout=timeout)

    monkeypatch.setattr("plugins.memory.ob_mybcat._AgentMemoryClient", factory)
    provider = ObMybcatAgentMemoryProvider()
    provider.initialize(
        "session-1",
        hermes_home=str(tmp_path),
        platform="telegram",
        agent_identity="default",
        user_id="user-1",
    )
    return provider, fake


def test_plugin_loader_can_load_ob_mybcat_provider(monkeypatch):
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_URL", "https://example.test/functions/v1/agent-memory-api")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_KEY", "test-secret-key")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_PROJECT_ID", "project-1")

    provider = load_memory_provider("ob_mybcat")

    assert provider is not None
    assert provider.name == "ob_mybcat"
    assert provider.is_available() is True


def test_is_available_requires_endpoint_and_key(monkeypatch):
    monkeypatch.delenv("OB_MYBCAT_AGENT_MEMORY_URL", raising=False)
    monkeypatch.delenv("OB1_AGENT_MEMORY_ENDPOINT", raising=False)
    monkeypatch.delenv("OB_MYBCAT_AGENT_MEMORY_KEY", raising=False)
    monkeypatch.delenv("OB1_AGENT_MEMORY_KEY", raising=False)

    provider = ObMybcatAgentMemoryProvider()
    assert provider.is_available() is False

    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_URL", "https://example.test/functions/v1/agent-memory-api")
    assert provider.is_available() is False

    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_KEY", "test-secret-key")
    assert provider.is_available() is False

    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID", "workspace-1")
    assert provider.is_available() is False

    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_PROJECT_ID", "project-1")
    assert provider.is_available() is True

    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_URL", "http://example.test/functions/v1/agent-memory-api")
    assert provider.is_available() is False


def test_config_round_trip_and_env_override(monkeypatch, tmp_path):
    (tmp_path / "ob_mybcat_agent_memory.json").write_text(
        json.dumps({"api_key": "existing-secret", "endpoint": "https://old.example/api?token=old"}),
        encoding="utf-8",
    )
    _save_ob_mybcat_config(
        {
            "endpoint": "https://config.example/functions/v1/agent-memory-api",
            "workspace_id": "workspace-from-config",
            "project_id": "project-from-config",
            "environment": "staging",
            "max_recall_results": 7,
            "auto_recall": False,
            "api_key": "should-not-persist",
            "access_token": "should-not-persist",
            "password": "should-not-persist",
        },
        str(tmp_path),
    )

    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_URL", "https://env.example/functions/v1/agent-memory-api")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID", "workspace-from-env")

    cfg = _load_ob_mybcat_config(str(tmp_path))

    assert cfg["endpoint"] == "https://env.example/functions/v1/agent-memory-api"
    assert cfg["workspace_id"] == "workspace-from-env"
    assert cfg["project_id"] == "project-from-config"
    assert cfg["max_recall_results"] == 7
    assert cfg["auto_recall"] is False
    raw_config = (tmp_path / "ob_mybcat_agent_memory.json").read_text(encoding="utf-8")
    assert "should-not-persist" not in raw_config
    assert "api_key" not in raw_config
    assert "access_token" not in raw_config
    assert "password" not in raw_config
    assert "existing-secret" not in raw_config
    assert "?token=" not in raw_config


def test_save_config_normalizes_existing_endpoint_query_when_saving_other_fields(tmp_path):
    (tmp_path / "ob_mybcat_agent_memory.json").write_text(
        json.dumps({"endpoint": "https://old.example/api?token=existing-secret", "workspace_id": "workspace-1"}),
        encoding="utf-8",
    )

    _save_ob_mybcat_config({"mirror_builtin_writes": True}, str(tmp_path))

    raw_config = (tmp_path / "ob_mybcat_agent_memory.json").read_text(encoding="utf-8")
    assert "?token=" not in raw_config
    assert "existing-secret" not in raw_config
    assert "https://old.example/api" in raw_config


@pytest.mark.parametrize("environment", ["live", "prod", "production", "main"])
def test_non_staging_environment_labels_fail_closed(monkeypatch, environment):
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_URL", "https://example.test/functions/v1/agent-memory-api")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_KEY", "test-secret-key")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_PROJECT_ID", "project-1")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_ENVIRONMENT", environment)
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_ALLOW_LIVE", "true")

    provider = ObMybcatAgentMemoryProvider()

    assert provider.is_available() is False


def test_post_setup_does_not_persist_credentials_or_activate_provider(tmp_path, capsys):
    provider = ObMybcatAgentMemoryProvider()
    config = {"memory": {"provider": ""}}

    provider.post_setup(str(tmp_path), config)

    output = capsys.readouterr().out
    assert "OB_MYBCAT_AGENT_MEMORY_KEY" in output
    assert config["memory"].get("provider") != "ob_mybcat"
    assert not (tmp_path / ".env").exists()


def test_clean_text_strips_attributed_memory_context_blocks():
    cleaned = _clean_text(
        '<memory-context source="ob_mybcat_agent_memory" surface="codex">Do not persist me</memory-context> Keep this.'
    )

    assert cleaned == "Keep this."


def test_prefetch_posts_recall_payload_and_formats_response(provider_with_client):
    provider, fake = provider_with_client
    fake.post_responses["/recall"] = {
        "request_id": "req-123",
        "memories": [
            {
                "id": "mem-1",
                "content": "Classic Vision Care uses EyeCloud as its EHR.",
                "review_status": "confirmed",
                "provenance": "user_confirmed",
                "use_policy": {
                    "can_use_as_instruction": True,
                    "can_use_as_evidence": True,
                    "requires_user_confirmation": False,
                },
                "source_refs": [{"type": "thought", "id": "thought-1"}],
            },
            {
                "id": "mem-2",
                "content": "Agent-written staging notes should remain pending evidence.",
                "review_status": "pending",
                "provenance": "generated",
                "use_policy": {
                    "can_use_as_instruction": True,
                    "can_use_as_evidence": True,
                    "requires_user_confirmation": True,
                },
            },
        ],
    }

    context = provider.prefetch("Classic Vision Care EHR", session_id="session-1")

    assert fake.posts[0]["path"] == "/recall"
    payload = fake.posts[0]["payload"]
    assert payload["schema_version"] == "openbrain.agent_memory.recall.v1"
    assert payload["query"] == "Classic Vision Care EHR"
    assert payload["workspace_id"] == "workspace-1"
    assert payload["project_id"] == "project-1"
    assert payload["session_id"] == "session-1"
    assert payload["runtime"]["name"] == "hermes"
    assert payload["runtime"]["platform"] == "telegram"
    assert payload["include_unconfirmed"] is False

    assert "OB_mybcat Agent Memory" in context
    assert "req-123" in context
    assert "Classic Vision Care uses EyeCloud" in context
    assert "instruction" in context
    assert "pending" in context
    assert "evidence" in context
    assert "[instruction | review:pending" not in context
    assert "[evidence | review:pending" in context


def test_recall_format_redacts_restricted_returned_content(provider_with_client):
    provider, fake = provider_with_client
    fake.post_responses["/recall"] = {
        "memories": [
            {
                "id": "mem-secret",
                "content": "OPENAI_API_KEY=should-not-appear",
                "review_status": "approved",
                "provenance": "user_confirmed",
                "use_policy": {"can_use_as_instruction": True, "can_use_as_evidence": True},
            }
        ]
    }

    tool_result = json.loads(provider.handle_tool_call("ob_mybcat_recall", {"query": "safe query"}))
    serialized = json.dumps(tool_result)

    assert "should-not-appear" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "redacted" in serialized.lower()


def test_writeback_defaults_to_pending_evidence_and_source_refs(provider_with_client):
    provider, fake = provider_with_client
    fake.post_responses["/writeback"] = {
        "saved": True,
        "memory_id": "mem-new",
        "review_status": "pending",
    }

    result = json.loads(
        provider.handle_tool_call(
            "ob_mybcat_writeback",
            {
                "content": "Decision: implement OB_mybcat as a staging-only Hermes MemoryProvider adapter.",
                "memory_type": "decision",
                "source_refs": [{"type": "artifact", "uri": "plans/ob-mybcat-agent-memory-provider-v1-plan.md"}],
            },
        )
    )

    assert result["saved"] is True
    assert result["memory_id"] == "mem-new"
    assert result["review_status"] == "pending"

    assert fake.posts[0]["path"] == "/writeback"
    payload = fake.posts[0]["payload"]
    assert payload["schema_version"] == "openbrain.agent_memory.writeback.v1"
    assert payload["workspace_id"] == "workspace-1"
    assert payload["project_id"] == "project-1"
    assert payload["review_status"] == "pending"
    assert payload["provenance"] == "generated"
    assert payload["memory_type"] == "decision"
    assert payload["use_policy"] == {
        "can_use_as_instruction": False,
        "can_use_as_evidence": True,
        "requires_user_confirmation": True,
        "do_not_inject_automatically": False,
    }
    assert payload["source_refs"] == [
        {"type": "artifact", "uri": "plans/ob-mybcat-agent-memory-provider-v1-plan.md"}
    ]


def test_tool_writeback_cannot_claim_trusted_provenance(provider_with_client):
    provider, fake = provider_with_client

    provider.handle_tool_call(
        "ob_mybcat_writeback",
        {
            "content": "Safe operational handoff note.",
            "memory_type": "handoff",
            "provenance": "user_confirmed",
        },
    )

    payload = fake.posts[0]["payload"]
    assert payload["provenance"] == "generated"
    assert payload["review_status"] == "pending"
    assert payload["use_policy"]["can_use_as_instruction"] is False


def test_writeback_blocks_obvious_secret_content(provider_with_client):
    provider, fake = provider_with_client

    result = json.loads(
        provider.handle_tool_call(
            "ob_mybcat_writeback",
            {"content": "OPENAI_API_KEY=sk-this-should-never-be-sent"},
        )
    )

    assert "error" in result
    assert "restricted" in result["error"].lower()
    assert fake.posts == []


def test_recall_blocks_restricted_query_before_http_call(provider_with_client):
    provider, fake = provider_with_client

    result = json.loads(
        provider.handle_tool_call(
            "ob_mybcat_recall",
            {"query": "OPENAI_API_KEY=sk-this-should-not-be-sent"},
        )
    )

    assert "error" in result
    assert "restricted" in result["error"].lower()
    assert fake.posts == []


def test_writeback_blocks_restricted_metadata_and_source_refs(provider_with_client):
    provider, fake = provider_with_client

    metadata_result = json.loads(
        provider.handle_tool_call(
            "ob_mybcat_writeback",
            {
                "content": "Safe operational note.",
                "metadata": {"access_token": "do-not-send"},
            },
        )
    )
    source_result = json.loads(
        provider.handle_tool_call(
            "ob_mybcat_writeback",
            {
                "content": "Safe operational note.",
                "source_refs": [{"type": "log", "uri": "Bearer should-not-be-sent"}],
            },
        )
    )

    assert "error" in metadata_result
    assert "restricted" in metadata_result["error"].lower()
    assert "error" in source_result
    assert "restricted" in source_result["error"].lower()
    assert fake.posts == []


def test_sync_turn_does_not_write_raw_transcripts_by_default(provider_with_client):
    provider, fake = provider_with_client

    provider.sync_turn("User asked for a plan", "Assistant produced a plan", session_id="session-1")

    assert fake.posts == []


def test_on_memory_write_mirrors_only_when_enabled(monkeypatch, tmp_path):
    fake = FakeAgentMemoryClient()
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_URL", "https://example.test/functions/v1/agent-memory-api")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_KEY", "test-secret-key")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_WORKSPACE_ID", "workspace-1")
    monkeypatch.setenv("OB_MYBCAT_AGENT_MEMORY_PROJECT_ID", "project-1")
    _save_ob_mybcat_config({"mirror_builtin_writes": True}, str(tmp_path))

    def factory(*, endpoint, api_key, timeout):
        return fake.configure(endpoint=endpoint, api_key=api_key, timeout=timeout)

    monkeypatch.setattr("plugins.memory.ob_mybcat._AgentMemoryClient", factory)
    provider = ObMybcatAgentMemoryProvider()
    provider.initialize("session-1", hermes_home=str(tmp_path), platform="cli")

    provider.on_memory_write(
        "add",
        "memory",
        "Hermes should treat OB_mybcat Agent Memory writebacks as pending evidence by default.",
        metadata={"source_tool": "memory"},
    )

    assert len(fake.posts) == 1
    payload = fake.posts[0]["payload"]
    assert fake.posts[0]["path"] == "/writeback"
    assert payload["memory_type"] == "hermes_builtin_memory"
    assert payload["metadata"]["target"] == "memory"
    assert payload["metadata"]["source_tool"] == "memory"
    assert payload["review_status"] == "pending"


def test_status_health_redacts_credentials(provider_with_client):
    provider, fake = provider_with_client
    provider._config["endpoint"] = "https://example.test/functions/v1/agent-memory-api?key=test-secret-key"
    fake.get_responses["/health"] = {"ok": True, "version": "test"}

    result = json.loads(provider.handle_tool_call("ob_mybcat_status", {}))

    assert result["configured"] is True
    assert result["health"] == {"ok": True, "version": "test"}
    serialized = json.dumps(result)
    assert "test-secret-key" not in serialized
    assert result["endpoint"] == "https://example.test/functions/v1/agent-memory-api?[redacted]"
    assert result["credential"] == "set"
