"""Carrega e salva a configuração da aplicação em config.json.

O arquivo fica ao lado do projeto (não é versionado — veja .gitignore) e
guarda qual provedor de LLM usar, a chave de API (ou caminho, no caso de um
servidor local) e parâmetros do agente.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

DEFAULT_CONFIG = {
    "provider": "anthropic",
    "anthropic": {
        "api_key": "",
        "model": "claude-sonnet-5",
        "computer_tool_version": "computer_20251124",
    },
    "openai_compatible": {
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
    },
    "agent": {
        "max_steps": 30,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return _deep_merge(DEFAULT_CONFIG, data)
        except (json.JSONDecodeError, OSError):
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(config: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
