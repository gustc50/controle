"""Orquestra a execução do provedor escolhido em uma thread separada, para
não travar a interface gráfica, e expõe filas thread-safe para logs e
screenshots.
"""

import queue
import threading
from typing import Optional

from . import config as config_module
from .providers.anthropic_provider import AnthropicComputerUseAgent
from .providers.base import AgentCallbacks
from .providers.openai_provider import OpenAICompatibleAgent

DONE_SENTINEL = "__DONE__"


class AgentController:
    def __init__(self):
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.screenshot_queue: "queue.Queue[str]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, instruction: str) -> bool:
        if self.is_running:
            return False
        if not instruction.strip():
            self.log_queue.put("Digite uma instrução antes de iniciar.")
            self.log_queue.put(DONE_SENTINEL)
            return False

        cfg = config_module.load_config()
        try:
            provider = self._build_provider(cfg)
        except Exception as e:
            self.log_queue.put(f"Erro na configuração: {e}")
            self.log_queue.put(DONE_SENTINEL)
            return False

        self._stop_event.clear()
        callbacks = AgentCallbacks(
            on_log=self.log_queue.put,
            on_screenshot=self.screenshot_queue.put,
        )

        def _run():
            try:
                provider.run(instruction, callbacks, self._stop_event.is_set)
            except Exception as e:
                self.log_queue.put(f"Erro inesperado: {e}")
            finally:
                self.log_queue.put(DONE_SENTINEL)

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop_event.set()

    def _build_provider(self, cfg: dict):
        provider_name = cfg.get("provider", "anthropic")
        max_steps = int(cfg.get("agent", {}).get("max_steps", 30))

        if provider_name == "anthropic":
            a = cfg["anthropic"]
            if not a.get("api_key"):
                raise ValueError("Configure a chave de API da Anthropic em Configurações.")
            return AnthropicComputerUseAgent(
                api_key=a["api_key"],
                model=a["model"],
                tool_version=a.get("computer_tool_version", "computer_20251124"),
                max_steps=max_steps,
            )

        if provider_name == "openai_compatible":
            o = cfg["openai_compatible"]
            if not o.get("api_key"):
                raise ValueError("Configure a chave de API em Configurações.")
            return OpenAICompatibleAgent(
                api_key=o["api_key"],
                base_url=o["base_url"],
                model=o["model"],
                max_steps=max_steps,
            )

        raise ValueError(f"Provedor desconhecido: {provider_name}")
