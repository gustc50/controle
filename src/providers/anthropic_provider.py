"""Provedor que usa a API da Anthropic (Claude) com a ferramenta nativa
"computer use" — Claude recebe screenshots e devolve ações de mouse/teclado.
"""

import time

import anthropic
import pyautogui

from .. import screen_control
from .base import AgentCallbacks, ComputerAgentProvider

SYSTEM_PROMPT = (
    "Você é um assistente que controla o computador do usuário através de "
    "capturas de tela e ações de mouse/teclado para completar a tarefa "
    "pedida. Analise cada screenshot com atenção antes de agir, confirme o "
    "resultado das suas ações olhando o próximo screenshot, e prefira "
    "passos pequenos e verificáveis. Quando a tarefa estiver concluída, "
    "responda apenas com texto (sem chamar mais nenhuma ferramenta) "
    "explicando o que foi feito."
)


def _derive_beta_header(tool_version: str) -> str:
    """Converte "computer_20251124" -> "computer-use-2025-11-24"."""
    digits = tool_version.rsplit("_", 1)[-1]
    if len(digits) == 8 and digits.isdigit():
        return f"computer-use-{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    return "computer-use-2025-11-24"


class AnthropicComputerUseAgent(ComputerAgentProvider):
    def __init__(self, api_key: str, model: str, tool_version: str = "computer_20251124", max_steps: int = 30):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.tool_version = tool_version
        self.beta_header = _derive_beta_header(tool_version)
        self.max_steps = max_steps

    def run(self, instruction: str, callbacks: AgentCallbacks, should_stop) -> None:
        width, height = screen_control.get_screen_size()
        tools = [
            {
                "type": self.tool_version,
                "name": "computer",
                "display_width_px": width,
                "display_height_px": height,
                "display_number": 1,
            }
        ]

        b64, _ = screen_control.take_screenshot_png_b64()
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": b64},
                    },
                ],
            }
        ]

        for step in range(1, self.max_steps + 1):
            if should_stop():
                callbacks.on_log("Parado pelo usuário.")
                return

            callbacks.on_log(f"Passo {step}/{self.max_steps}: consultando o modelo...")
            try:
                response = self.client.beta.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    betas=[self.beta_header],
                    tools=tools,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                )
            except anthropic.APIStatusError as e:
                callbacks.on_log(f"Erro da API: {e.status_code} - {e.message}")
                return
            except anthropic.APIConnectionError as e:
                callbacks.on_log(f"Erro de conexão: {e}")
                return

            messages.append({"role": "assistant", "content": response.content})

            for block in response.content:
                if block.type == "text" and block.text.strip():
                    callbacks.on_log(f"Modelo: {block.text.strip()}")

            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                callbacks.on_log("Tarefa concluída.")
                return

            tool_results = []
            stopped = False
            for tu in tool_uses:
                if should_stop():
                    callbacks.on_log("Parado pelo usuário.")
                    stopped = True
                    break
                try:
                    content = self._execute_action(tu.input, callbacks)
                except pyautogui.FailSafeException:
                    callbacks.on_log(
                        "Fail-safe ativado (mouse movido para o canto da tela) — interrompendo."
                    )
                    stopped = True
                    break
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": tu.id, "content": content}
                )

            if stopped:
                return

            messages.append({"role": "user", "content": tool_results})

        callbacks.on_log(f"Limite de {self.max_steps} passos atingido — parando.")

    def _execute_action(self, action_input: dict, callbacks: AgentCallbacks):
        action = action_input.get("action")
        callbacks.on_log(f"Ação: {action} {action_input}")

        try:
            if action == "screenshot":
                pass
            elif action == "left_click":
                x, y = action_input["coordinate"]
                screen_control.click(x, y, "left")
            elif action == "right_click":
                x, y = action_input["coordinate"]
                screen_control.click(x, y, "right")
            elif action == "middle_click":
                x, y = action_input["coordinate"]
                screen_control.click(x, y, "middle")
            elif action == "double_click":
                x, y = action_input["coordinate"]
                screen_control.click(x, y, "left", clicks=2)
            elif action == "triple_click":
                x, y = action_input["coordinate"]
                screen_control.click(x, y, "left", clicks=3)
            elif action == "mouse_move":
                x, y = action_input["coordinate"]
                screen_control.move_mouse(x, y)
            elif action == "left_click_drag":
                start = action_input.get("start_coordinate")
                x2, y2 = action_input["coordinate"]
                if start:
                    x1, y1 = start
                else:
                    x1, y1 = screen_control.cursor_position()
                screen_control.drag(x1, y1, x2, y2)
            elif action == "type":
                screen_control.type_text(action_input.get("text", ""))
            elif action == "key":
                screen_control.key_press(action_input.get("text", ""))
            elif action == "hold_key":
                screen_control.hold_key(
                    action_input.get("text", ""), float(action_input.get("duration", 0.5))
                )
            elif action == "scroll":
                coord = action_input.get("coordinate")
                x, y = coord if coord else screen_control.cursor_position()
                direction = action_input.get("scroll_direction", "down")
                amount = action_input.get("scroll_amount", 3)
                screen_control.scroll_by_direction(x, y, direction, amount)
            elif action == "wait":
                screen_control.wait(float(action_input.get("duration", 1)))
            elif action == "cursor_position":
                pass
            else:
                callbacks.on_log(f"Ação desconhecida ignorada: {action}")
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            callbacks.on_log(f"Erro ao executar ação '{action}': {e}")

        time.sleep(0.3)
        b64, _ = screen_control.take_screenshot_png_b64()
        callbacks.on_screenshot(b64)

        content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}]
        if action == "cursor_position":
            x, y = screen_control.cursor_position()
            content.insert(0, {"type": "text", "text": f"Posição do cursor: ({x}, {y})"})
        return content
