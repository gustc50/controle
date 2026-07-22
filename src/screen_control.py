"""Captura de tela e controle de mouse/teclado.

Usa pyautogui para tirar screenshots e executar ações — assim as coordenadas
retornadas pela LLM (baseadas no screenshot) e as coordenadas usadas para
clicar/mover o mouse ficam sempre no mesmo sistema de referência.
"""

import base64
import io
import sys
import time
from typing import Optional

import pyautogui
from PIL import Image

# Mover o mouse para o canto superior esquerdo da tela interrompe qualquer
# ação em andamento (pyautogui.FailSafeException) — um kill-switch manual.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

_IS_MAC = sys.platform == "darwin"

# Nomes de teclas no estilo X11/xdotool (usados pela ferramenta "computer use"
# da Anthropic e por convenção geral) mapeados para os nomes que o pyautogui
# espera.
_KEY_MAP = {
    "return": "enter",
    "enter": "enter",
    "escape": "esc",
    "esc": "esc",
    "backspace": "backspace",
    "delete": "delete",
    "tab": "tab",
    "space": "space",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "page_up": "pageup",
    "pageup": "pageup",
    "page_down": "pagedown",
    "pagedown": "pagedown",
    "insert": "insert",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "win",
    "win": "win",
    "cmd": "command",
    "command": "command",
    "meta": "win",
}
for _i in range(1, 13):
    _KEY_MAP[f"f{_i}"] = f"f{_i}"


def _normalize_key(key: str) -> str:
    key = key.strip()
    return _KEY_MAP.get(key.lower(), key.lower())


def get_screen_size():
    return pyautogui.size()


def cursor_position():
    return pyautogui.position()


def take_screenshot_png_b64(max_dimension: Optional[int] = None):
    """Tira um screenshot e retorna (base64_png, (largura, altura))."""
    img = pyautogui.screenshot()
    if max_dimension and max(img.size) > max_dimension:
        img.thumbnail((max_dimension, max_dimension), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8"), img.size


def move_mouse(x: int, y: int, duration: float = 0.15):
    pyautogui.moveTo(x, y, duration=duration)


def click(x: int, y: int, button: str = "left", clicks: int = 1):
    pyautogui.click(x, y, button=button, clicks=clicks, interval=0.08)


def drag(x1: int, y1: int, x2: int, y2: int, duration: float = 0.3, button: str = "left"):
    pyautogui.moveTo(x1, y1)
    pyautogui.dragTo(x2, y2, duration=duration, button=button)


def type_text(text: str):
    """Digita texto usando a área de transferência (copiar/colar).

    pyautogui.typewrite só cobre um conjunto limitado de teclas ASCII e falha
    com acentos e caracteres não latinos — copiar/colar funciona para
    qualquer texto, independente do idioma.
    """
    if not text:
        return
    try:
        import pyperclip

        previous = None
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("command", "v") if _IS_MAC else pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        if previous is not None:
            try:
                pyperclip.copy(previous)
            except Exception:
                pass
    except Exception:
        # Sem acesso à área de transferência: melhor esforço com typewrite.
        pyautogui.typewrite(text, interval=0.01)


def key_press(combo: str):
    """Pressiona uma tecla ou combinação, ex.: "Return", "ctrl+c", "alt+Tab"."""
    if not combo:
        return
    keys = [_normalize_key(part) for part in combo.split("+") if part.strip()]
    if not keys:
        return
    if len(keys) == 1:
        pyautogui.press(keys[0])
    else:
        pyautogui.hotkey(*keys)


def hold_key(combo: str, duration: float = 0.5):
    keys = [_normalize_key(part) for part in combo.split("+") if part.strip()]
    if not keys:
        return
    for k in keys:
        pyautogui.keyDown(k)
    time.sleep(max(0.0, duration))
    for k in reversed(keys):
        pyautogui.keyUp(k)


def scroll_by_direction(x: int, y: int, direction: str, amount: int = 3):
    """Rola a tela na posição (x, y). `direction`: up/down/left/right."""
    move_mouse(x, y, duration=0)
    magnitude = max(1, int(amount)) * 20
    if direction == "up":
        pyautogui.scroll(magnitude)
    elif direction == "down":
        pyautogui.scroll(-magnitude)
    elif direction == "left":
        pyautogui.hscroll(-magnitude)
    elif direction == "right":
        pyautogui.hscroll(magnitude)


def scroll_xy(x: int, y: int, dx: int = 0, dy: int = 0):
    """Rola a tela: dy positivo = para baixo, dx positivo = para a direita."""
    move_mouse(x, y, duration=0)
    if dy:
        pyautogui.scroll(-dy)
    if dx:
        pyautogui.hscroll(dx)


def wait(seconds: float):
    time.sleep(max(0.0, seconds))
