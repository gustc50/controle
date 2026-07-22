# Controle de Tela por IA

Aplicação desktop que tira capturas de tela, envia para uma LLM externa
(via API ou servidor local) e executa na tela as ações de mouse/teclado que
o modelo decidir, para cumprir uma instrução em texto livre.

## Como funciona

1. Você digita uma instrução na aba **Controle** (ex.: "abra o navegador e
   pesquise o clima de hoje").
2. A aplicação tira um screenshot e envia, junto com a instrução, para a
   LLM configurada.
3. O modelo responde com uma ação (clique, digitar texto, tecla, rolar a
   tela, etc.), a aplicação executa essa ação, tira um novo screenshot e
   manda de volta — em loop — até o modelo considerar a tarefa concluída,
   até você clicar em **Parar**, ou até atingir o limite de passos.

## Provedores suportados (aba Configurações)

- **Anthropic (Claude)** — usa a ferramenta nativa `computer use`, feita
  especificamente para controlar telas. É o modo mais preciso.
- **Compatível com OpenAI** — funciona tanto com a API oficial da OpenAI
  quanto com qualquer servidor local que exponha um endpoint compatível
  (Ollama, LM Studio, vLLM, text-generation-webui etc.). Basta trocar o
  "Endereço base" para o endereço do servidor local, por exemplo
  `http://localhost:11434/v1`. O modelo escolhido precisa suportar visão
  (imagens) e *function calling*.

Cada seção tem um botão **Testar conexão** para validar a chave/endereço
antes de usar.

## Instalação

No **Linux**, instale antes os pacotes de sistema (a interface usa Tkinter, e
a captura de tela via `pyautogui` depende do Tkinter e de uma ferramenta de
screenshot):

```bash
sudo apt install python3-tk scrot
```

Depois:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Uso

**Windows:** dê duplo clique em `iniciar.bat` — na primeira vez ele cria o
ambiente virtual e instala as dependências automaticamente; nas próximas
apenas abre o programa.

**Linux/macOS:**

```bash
python main.py
```

1. Vá até a aba **Configurações**, escolha o provedor, preencha a chave de
   API (ou o endereço do servidor local) e o modelo, e clique em
   **Salvar configurações**.
2. Volte para a aba **Controle**, digite a instrução e clique em
   **▶ Iniciar**.
3. Para interromper a qualquer momento: clique em **■ Parar** ou mova o
   mouse rapidamente para o canto superior esquerdo da tela (fail-safe do
   `pyautogui` — interrompe qualquer ação imediatamente).

## Avisos importantes

- **Isso controla o mouse e o teclado de verdade.** Use com atenção,
  especialmente em tarefas que envolvam exclusão de arquivos, envio de
  mensagens, compras ou qualquer ação difícil de desfazer.
- A chave de API fica salva em `config.json`, que **não é** versionado
  (está no `.gitignore`) — nunca compartilhe esse arquivo.
- No **Linux**, o controle de mouse/teclado via `pyautogui` funciona em
  sessões X11; em Wayland pode não funcionar dependendo da distribuição.
- No **macOS**, é necessário conceder permissão de "Acessibilidade" (e
  "Gravação de tela") ao terminal/aplicativo em Preferências do Sistema.
- No **Windows** normalmente funciona sem configuração adicional.
- O limite de "passos" em Configurações existe para evitar que o agente
  fique executando ações indefinidamente em caso de erro.

## Estrutura do projeto

```
main.py                        ponto de entrada
iniciar.bat                    atalho para iniciar no Windows
config.example.json            modelo de configuração
src/
  config.py                    carregar/salvar config.json
  screen_control.py             screenshot + mouse/teclado (pyautogui)
  agent.py                      roda o provedor em uma thread + filas
  gui.py                        interface Tkinter (Controle / Configurações)
  providers/
    base.py                     interface comum
    anthropic_provider.py       loop usando a ferramenta "computer use"
    openai_provider.py          loop genérico via function calling
```
