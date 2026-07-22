"""Interface comum entre os provedores de LLM que controlam a tela."""

from abc import ABC, abstractmethod
from typing import Callable


class AgentCallbacks:
    """Callbacks usados pelo provedor para reportar progresso à interface."""

    def __init__(self, on_log: Callable[[str], None], on_screenshot: Callable[[str], None]):
        self.on_log = on_log
        self.on_screenshot = on_screenshot


class ComputerAgentProvider(ABC):
    @abstractmethod
    def run(self, instruction: str, callbacks: AgentCallbacks, should_stop: Callable[[], bool]) -> None:
        """Executa a instrução até concluir, atingir o limite de passos ou
        `should_stop()` retornar True."""
        raise NotImplementedError
