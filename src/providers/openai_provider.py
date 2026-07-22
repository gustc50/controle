"""Provedor genérico para qualquer endpoint compatível com a API de "chat
completions" da OpenAI — a própria OpenAI (base_url padrão) ou um servidor
local (Ollama, LM Studio, vLLM, text-generation-webui etc. apontando a
`base_url` para o endereço local).

Como esses modelos não têm uma ferramenta nativa de "controle de tela" como
a da Anthropic, definimos uma ferramenta (function calling) própria para as
ações de mouse/teclado.
"""

import json
import time

import pyautogui
import requests

from .. import screen_control
from .base import AgentCallbacks, ComputerAgentProvider

SYSTEM_PROMPT = (
    "Você controla o computador do usuário através de capturas de tela e "
    "ações de mouse/teclado. A cada passo você recebe uma imagem mostrando "
    "o estado atual da tela. Escolha exatamente UMA ação por vez chamando a "
    "ferramenta `computer_action`, observe o resultado no próximo "
    "screenshot antes de continuar, e prefira passos pequenos e "
    "verificáveis. Quando a tarefa pedida estiver concluída, chame a "
    "ferramenta `task_finished` com um resumo curto do que foi feito."
)

ACTIONS_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "computer_action",
            "description": "Executa uma ação de mouse ou teclado na tela do computador.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": [
                            "left_click",
                            "right_click",
                            "double_click",
                            "move_mouse",
                            "drag",
                            "type",
                            "key",
                            "scroll",
                            "wait",
                        ],
                        "description": "Tipo de ação a executar.",
                    },
                    "x": {"type": "integer", "description": "Coordenada X em pixels."},
                    "y": {"type": "integer", "description": "Coordenada Y em pixels."},
                    "x2": {"type": "integer", "description": "X de destino (apenas para 'drag')."},
                    "y2": {"type": "integer", "description": "Y de destino (apenas para 'drag')."},
                    "text": {
                        "type": "string",
                        "description": (
                            "Texto a digitar (ação 'type'), ou nome da tecla/combinação a "
                            "pressionar (ação 'key'), ex.: 'Return', 'ctrl+c', 'alt+Tab'."
                        ),
                    },
                    "scroll_dx": {
                        "type": "integer",
                        "description": "Rolagem horizontal: positivo = direita, negativo = esquerda.",
                    },
                    "scroll_dy": {
                        "type": "integer",
                        "description": "Rolagem vertical: positivo = para baixo, negativo = para cima.",
                    },
                    "duration": {"type": "number", "description": "Duração em segundos (ação 'wait')."},
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_finished",
            "description": "Chame esta função quando a tarefa pedida já tiver sido concluída.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Resumo curto do que foi feito."}
                },
                "required": ["summary"],
            },
        },
    },
]


class OpenAICompatibleAgent(ComputerAgentProvider):
    def __init__(self, api_key: str, base_url: str, model: str, max_steps: int = 30):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_steps = max_steps

    def _chat(self, messages):
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "tools": ACTIONS_TOOLS,
                "tool_choice": "auto",
                "max_tokens": 1024,
            },
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()

    def run(self, instruction: str, callbacks: AgentCallbacks, should_stop) -> None:
        width, height = screen_control.get_screen_size()
        b64, _ = screen_control.take_screenshot_png_b64()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Tarefa: {instruction}\nResolução da tela: {width}x{height} pixels.",
                    },
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ],
            },
        ]

        for step in range(1, self.max_steps + 1):
            if should_stop():
                callbacks.on_log("Parado pelo usuário.")
                return

            callbacks.on_log(f"Passo {step}/{self.max_steps}: consultando o modelo...")
            try:
                data = self._chat(messages)
            except requests.RequestException as e:
                callbacks.on_log(f"Erro de conexão/API: {e}")
                return

            if "error" in data:
                callbacks.on_log(f"Erro da API: {data['error']}")
                return

            msg = data["choices"][0]["message"]
            messages.append(msg)

            content_text = msg.get("content")
            if content_text:
                callbacks.on_log(f"Modelo: {content_text}")

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                callbacks.on_log("Tarefa concluída (o modelo não pediu mais ações).")
                return

            finished = False
            for tc in tool_calls:
                if should_stop():
                    callbacks.on_log("Parado pelo usuário.")
                    return

                fn_name = tc["function"]["name"]
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}

                if fn_name == "task_finished":
                    callbacks.on_log(f"Concluído: {args.get('summary', '')}")
                    finished = True
                    result_text = "ok"
                else:
                    try:
                        result_text = self._execute_action(args, callbacks)
                    except pyautogui.FailSafeException:
                        callbacks.on_log(
                            "Fail-safe ativado (mouse movido para o canto da tela) — interrompendo."
                        )
                        return

                messages.append(
                    {"role": "tool", "tool_call_id": tc["id"], "content": result_text}
                )

            if finished:
                return

            b64, _ = screen_control.take_screenshot_png_b64()
            callbacks.on_screenshot(b64)
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                    ],
                }
            )

        callbacks.on_log(f"Limite de {self.max_steps} passos atingido — parando.")

    def _execute_action(self, args: dict, callbacks: AgentCallbacks) -> str:
        action = args.get("action")
        callbacks.on_log(f"Ação: {action} {args}")

        try:
            if action == "left_click":
                screen_control.click(args["x"], args["y"], "left")
            elif action == "right_click":
                screen_control.click(args["x"], args["y"], "right")
            elif action == "double_click":
                screen_control.click(args["x"], args["y"], "left", clicks=2)
            elif action == "move_mouse":
                screen_control.move_mouse(args["x"], args["y"])
            elif action == "drag":
                x1, y1 = args.get("x"), args.get("y")
                if x1 is None or y1 is None:
                    x1, y1 = screen_control.cursor_position()
                screen_control.drag(x1, y1, args["x2"], args["y2"])
            elif action == "type":
                screen_control.type_text(args.get("text", ""))
            elif action == "key":
                screen_control.key_press(args.get("text", ""))
            elif action == "scroll":
                x, y = args.get("x"), args.get("y")
                if x is None or y is None:
                    x, y = screen_control.cursor_position()
                screen_control.scroll_xy(x, y, args.get("scroll_dx", 0), args.get("scroll_dy", 0))
            elif action == "wait":
                screen_control.wait(float(args.get("duration", 1)))
            else:
                return f"ação desconhecida: {action}"
        except pyautogui.FailSafeException:
            raise
        except Exception as e:
            return f"erro ao executar ação: {e}"

        time.sleep(0.2)
        return "ação executada com sucesso"
