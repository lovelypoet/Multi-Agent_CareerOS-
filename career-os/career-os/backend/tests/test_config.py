from app.core.config import Settings


def test_llm_provider_defaults_to_local_ollama(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "ollama"
