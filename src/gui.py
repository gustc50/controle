"""Interface gráfica (Tkinter) com duas abas:

- "Controle": onde o usuário digita as instruções em texto livre e
  acompanha o que o agente está fazendo (log + miniatura do último
  screenshot).
- "Configurações": onde ficam a chave/endereço da API e os parâmetros do
  provedor de LLM (Anthropic ou compatível com OpenAI/local).
"""

import base64
import io
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from . import config as config_module
from .agent import DONE_SENTINEL, AgentController

POLL_INTERVAL_MS = 150
THUMBNAIL_MAX_WIDTH = 420


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Controle de Tela por IA")
        self.geometry("800x700")
        self.minsize(620, 480)

        self.controller = AgentController()
        self.config_data = config_module.load_config()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        self.control_tab = ControlTab(notebook, self)
        self.settings_tab = SettingsTab(notebook, self)

        notebook.add(self.control_tab, text="Controle")
        notebook.add(self.settings_tab, text="Configurações")

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(POLL_INTERVAL_MS, self._poll_queues)

    def _poll_queues(self):
        self.control_tab.drain_queues()
        self.after(POLL_INTERVAL_MS, self._poll_queues)

    def _on_close(self):
        if self.controller.is_running:
            if not messagebox.askyesno(
                "Sair", "O agente ainda está em execução. Parar e sair mesmo assim?"
            ):
                return
            self.controller.stop()
        self.destroy()


class ControlTab(ttk.Frame):
    def __init__(self, parent, app: App):
        super().__init__(parent, padding=10)
        self.app = app
        self._current_thumb = None

        ttk.Label(
            self,
            text="Digite abaixo o que você quer que a IA faça na tela do computador:",
        ).pack(anchor="w")

        self.instruction_text = tk.Text(self, height=5, wrap="word")
        self.instruction_text.pack(fill="x", pady=(4, 8))
        self.instruction_text.focus_set()

        button_row = ttk.Frame(self)
        button_row.pack(fill="x")

        self.start_button = ttk.Button(button_row, text="▶ Iniciar", command=self._on_start)
        self.start_button.pack(side="left")

        self.stop_button = ttk.Button(
            button_row, text="■ Parar", command=self._on_stop, state="disabled"
        )
        self.stop_button.pack(side="left", padx=(8, 0))

        self.status_var = tk.StringVar(value="Parado.")
        ttk.Label(button_row, textvariable=self.status_var, foreground="#555").pack(
            side="left", padx=12
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(10, 0))
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        log_frame = ttk.LabelFrame(body, text="Log de execução")
        log_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.log_text = tk.Text(log_frame, wrap="word", state="disabled", height=20)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        preview_frame = ttk.LabelFrame(body, text="Última captura de tela")
        preview_frame.grid(row=0, column=1, sticky="nsew")
        self.preview_label = ttk.Label(
            preview_frame, text="(sem captura ainda)", anchor="center"
        )
        self.preview_label.pack(fill="both", expand=True, padx=4, pady=4)

        note = (
            "Dica de segurança: mover o mouse rapidamente para o canto "
            "superior esquerdo da tela interrompe qualquer ação em andamento."
        )
        ttk.Label(self, text=note, foreground="#888", wraplength=720).pack(
            anchor="w", pady=(8, 0)
        )

    def _on_start(self):
        instruction = self.instruction_text.get("1.0", "end").strip()
        if not instruction:
            messagebox.showwarning("Instrução vazia", "Digite o que a IA deve fazer.")
            return

        self._append_log(f"Iniciando: {instruction}")
        started = self.app.controller.start(instruction)
        if started:
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
            self.status_var.set("Em execução...")

    def _on_stop(self):
        self.app.controller.stop()
        self.status_var.set("Parando...")
        self.stop_button.configure(state="disabled")

    def drain_queues(self):
        controller = self.app.controller

        while True:
            try:
                msg = controller.log_queue.get_nowait()
            except queue.Empty:
                break
            if msg == DONE_SENTINEL:
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                self.status_var.set("Parado.")
            else:
                self._append_log(msg)

        while True:
            try:
                b64 = controller.screenshot_queue.get_nowait()
            except queue.Empty:
                break
            self._update_preview(b64)

    def _append_log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _update_preview(self, b64: str):
        try:
            data = base64.b64decode(b64)
            img = Image.open(io.BytesIO(data))
            ratio = THUMBNAIL_MAX_WIDTH / img.width
            img = img.resize((THUMBNAIL_MAX_WIDTH, int(img.height * ratio)))
            photo = ImageTk.PhotoImage(img)
        except Exception:
            return
        self.preview_label.configure(image=photo, text="")
        self._current_thumb = photo  # evita garbage collection


class SettingsTab(ttk.Frame):
    """Aba de configurações.

    O conteúdo fica dentro de um Canvas rolável: assim, mesmo em janelas
    pequenas ou com fonte/DPI maior, o botão "Salvar configurações" no final
    nunca fica cortado/inacessível — o usuário só precisa rolar para vê-lo.
    """

    def __init__(self, parent, app: App):
        super().__init__(parent, padding=0)
        self.app = app
        cfg = app.config_data

        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        vscroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        inner = ttk.Frame(canvas, padding=10)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _sync_inner_width(event):
            canvas.itemconfigure(inner_id, width=event.width)

        inner.bind("<Configure>", _sync_scrollregion)
        canvas.bind("<Configure>", _sync_inner_width)

        def _on_mousewheel(event):
            # Só rola se o ponteiro estiver sobre esta aba (evita "roubar" o
            # scroll de outros widgets/abas, já que o bind é global).
            if not str(event.widget).startswith(str(self)):
                return
            if event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")
            else:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Windows/macOS
        canvas.bind_all("<Button-4>", _on_mousewheel)  # Linux (scroll para cima)
        canvas.bind_all("<Button-5>", _on_mousewheel)  # Linux (scroll para baixo)

        self._build_form(inner, cfg)

    def _build_form(self, container, cfg):
        ttk.Label(
            container,
            text="Escolha e configure o provedor de LLM externo (via API ou local):",
        ).pack(anchor="w", pady=(0, 8))

        self.provider_var = tk.StringVar(value=cfg.get("provider", "anthropic"))
        provider_row = ttk.Frame(container)
        provider_row.pack(fill="x", pady=(0, 12))
        ttk.Radiobutton(
            provider_row,
            text="Anthropic (Claude) — ferramenta nativa de controle de tela",
            variable=self.provider_var,
            value="anthropic",
        ).pack(anchor="w")
        ttk.Radiobutton(
            provider_row,
            text="Compatível com OpenAI (nuvem ou servidor local: Ollama, LM Studio, vLLM...)",
            variable=self.provider_var,
            value="openai_compatible",
        ).pack(anchor="w")

        # --- Anthropic ---
        a_frame = ttk.LabelFrame(container, text="Anthropic (Claude)")
        a_frame.pack(fill="x", pady=(0, 12))
        a_cfg = cfg["anthropic"]

        self.anthropic_key_var = tk.StringVar(value=a_cfg.get("api_key", ""))
        self._labeled_secret_entry(a_frame, "Chave de API:", self.anthropic_key_var, row=0)

        self.anthropic_model_var = tk.StringVar(value=a_cfg.get("model", "claude-sonnet-5"))
        self._labeled_entry(a_frame, "Modelo:", self.anthropic_model_var, row=1)

        self.anthropic_tool_var = tk.StringVar(
            value=a_cfg.get("computer_tool_version", "computer_20251124")
        )
        self._labeled_entry(a_frame, "Versão da ferramenta computer use:", self.anthropic_tool_var, row=2)

        ttk.Button(
            a_frame, text="Testar conexão", command=self._test_anthropic
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 8))

        # --- OpenAI-compatible / local ---
        o_frame = ttk.LabelFrame(container, text="Compatível com OpenAI / servidor local")
        o_frame.pack(fill="x", pady=(0, 12))
        o_cfg = cfg["openai_compatible"]

        self.openai_key_var = tk.StringVar(value=o_cfg.get("api_key", ""))
        self._labeled_secret_entry(o_frame, "Chave de API (use qualquer valor se o servidor local não exigir):", self.openai_key_var, row=0)

        self.openai_base_url_var = tk.StringVar(
            value=o_cfg.get("base_url", "https://api.openai.com/v1")
        )
        self._labeled_entry(
            o_frame,
            "Endereço base (ex.: http://localhost:11434/v1 para local):",
            self.openai_base_url_var,
            row=1,
        )

        self.openai_model_var = tk.StringVar(value=o_cfg.get("model", "gpt-4o"))
        self._labeled_entry(o_frame, "Modelo:", self.openai_model_var, row=2)

        ttk.Button(
            o_frame, text="Testar conexão", command=self._test_openai_compatible
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=(4, 8))

        # --- Agent settings ---
        agent_frame = ttk.LabelFrame(container, text="Comportamento do agente")
        agent_frame.pack(fill="x", pady=(0, 12))
        ttk.Label(agent_frame, text="Máximo de passos por tarefa:").grid(
            row=0, column=0, sticky="w", padx=6, pady=6
        )
        self.max_steps_var = tk.IntVar(value=int(cfg.get("agent", {}).get("max_steps", 30)))
        ttk.Spinbox(
            agent_frame, from_=1, to=200, textvariable=self.max_steps_var, width=8
        ).grid(row=0, column=1, sticky="w", padx=6, pady=6)

        save_row = ttk.Frame(container)
        save_row.pack(fill="x", pady=(4, 0))
        self.save_status_var = tk.StringVar(value="")
        ttk.Label(save_row, textvariable=self.save_status_var, foreground="#2a7a2a").pack(
            side="left"
        )
        ttk.Button(save_row, text="Salvar configurações", command=self._save).pack(side="right")

    def _labeled_entry(self, parent, label, var, row):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=6)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=6, pady=6)

    def _labeled_secret_entry(self, parent, label, var, row):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=6)
        entry = ttk.Entry(parent, textvariable=var, show="•")
        entry.grid(row=row, column=1, sticky="ew", padx=(6, 4), pady=6)

        show_var = tk.BooleanVar(value=False)

        def toggle():
            entry.configure(show="" if show_var.get() else "•")

        ttk.Checkbutton(parent, text="mostrar", variable=show_var, command=toggle).grid(
            row=row, column=2, sticky="w", padx=(0, 6), pady=6
        )

    def _collect_config(self) -> dict:
        return {
            "provider": self.provider_var.get(),
            "anthropic": {
                "api_key": self.anthropic_key_var.get().strip(),
                "model": self.anthropic_model_var.get().strip(),
                "computer_tool_version": self.anthropic_tool_var.get().strip(),
            },
            "openai_compatible": {
                "api_key": self.openai_key_var.get().strip(),
                "base_url": self.openai_base_url_var.get().strip(),
                "model": self.openai_model_var.get().strip(),
            },
            "agent": {"max_steps": int(self.max_steps_var.get())},
        }

    def _save(self):
        cfg = self._collect_config()
        config_module.save_config(cfg)
        self.app.config_data = cfg

        provider = cfg["provider"]
        model = cfg[provider].get("model", "")
        provider_label = "Anthropic" if provider == "anthropic" else "Compatível com OpenAI"
        self.save_status_var.set(f"✓ Salvo — provedor ativo: {provider_label} (modelo: {model})")

        messagebox.showinfo(
            "Configurações",
            f"Configurações salvas com sucesso.\n\nProvedor ativo: {provider_label}\nModelo: {model}",
        )

    def _test_anthropic(self):
        api_key = self.anthropic_key_var.get().strip()
        model = self.anthropic_model_var.get().strip()
        if not api_key or not model:
            messagebox.showwarning("Teste", "Preencha a chave de API e o modelo antes de testar.")
            return

        def run_test():
            try:
                import anthropic

                client = anthropic.Anthropic(api_key=api_key)
                client.messages.create(
                    model=model, max_tokens=8, messages=[{"role": "user", "content": "ping"}]
                )
                self.after(0, lambda: messagebox.showinfo("Teste", "Conexão com a Anthropic OK!"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Teste", f"Falha na conexão: {e}"))

        threading.Thread(target=run_test, daemon=True).start()

    def _test_openai_compatible(self):
        api_key = self.openai_key_var.get().strip()
        base_url = self.openai_base_url_var.get().strip()
        model = self.openai_model_var.get().strip()
        if not base_url or not model:
            messagebox.showwarning("Teste", "Preencha o endereço base e o modelo antes de testar.")
            return

        def run_test():
            try:
                import requests

                resp = requests.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 8,
                    },
                    timeout=20,
                )
                resp.raise_for_status()
                self.after(0, lambda: messagebox.showinfo("Teste", "Conexão OK!"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Teste", f"Falha na conexão: {e}"))

        threading.Thread(target=run_test, daemon=True).start()
