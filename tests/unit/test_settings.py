from pathlib import Path

from getnet_multi_agent.core.settings import ENV_FILE_FIELDS, Settings

ROOT = Path(__file__).resolve().parents[2]


def test_fr_054_env_example_lists_exactly_the_settings_fields():
    keys = [
        line.split("=", 1)[0]
        for line in (ROOT / ".env.example").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert sorted(keys) == sorted(ENV_FILE_FIELDS)
    assert set(ENV_FILE_FIELDS) <= set(Settings.model_fields)


def test_fr_054_secrets_are_empty_in_env_example():
    values = dict(
        line.split("=", 1) for line in (ROOT / ".env.example").read_text().splitlines() if "=" in line
    )
    for secret in ("GEMINI_API_KEY", "JWT_SECRET", "PSEUDONYM_KEY"):
        assert values[secret] == ""


def test_fr_054_process_env_overrides(monkeypatch):
    monkeypatch.setenv("RAG_TOP_K", "9")
    monkeypatch.setenv("LLM_MODE", "stub")
    s = Settings(_env_file=None)
    assert s.RAG_TOP_K == 9 and s.LLM_MODE == "stub"
