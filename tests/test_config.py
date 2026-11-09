from pathlib import Path

import pytest
import yaml

from src.config import PROJECT_ROOT, ConfigError, load_config

ROOT_CONFIG = PROJECT_ROOT / "config.yaml"

ENV = {
    "GROQ_API_KEY": "gsk-test-key-1234",
    "LLM_MODEL": "qwen/qwen3.8-27b",
}


def _raw() -> dict:
    return yaml.safe_load(ROOT_CONFIG.read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_repo_config_loads():
    config = load_config(ROOT_CONFIG, ENV)
    assert len(config.corpus) == 5
    assert config.provider == "groq"
    assert config.embedding_model == "gemini-embedding-001"
    assert config.collection == "hdfc_facts"
    assert config.disclaimer == "Facts-only. No investment advice."
    assert config.llm_model == "qwen/qwen3.8-27b"


def test_bad_url_names_the_field(tmp_path: Path):
    data = _raw()
    data["corpus"][1]["url"] = "https://example.com/not-allowed"
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data), ENV)
    assert exc.value.field == "corpus[1].url"


def test_unknown_provider_names_the_field(tmp_path: Path):
    data = _raw()
    data["llm"]["provider"] = "cohere"
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data), ENV)
    assert exc.value.field == "llm.provider"


def test_missing_key_names_the_field():
    env = {"LLM_MODEL": "qwen/qwen3.8-27b"}
    with pytest.raises(ConfigError) as exc:
        load_config(ROOT_CONFIG, env)
    assert exc.value.field == "GROQ_API_KEY"


def test_empty_model_names_the_field():
    env = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "  "}
    with pytest.raises(ConfigError) as exc:
        load_config(ROOT_CONFIG, env)
    assert exc.value.field == "LLM_MODEL"


def test_provider_switch_requires_that_providers_key(tmp_path: Path):
    data = _raw()
    data["llm"]["provider"] = "openai"
    env = {"GROQ_API_KEY": "gsk-test-key-1234", "LLM_MODEL": "qwen/qwen3.8-27b"}
    with pytest.raises(ConfigError) as exc:
        load_config(_write(tmp_path, data), env)
    assert exc.value.field == "OPENAI_API_KEY"
