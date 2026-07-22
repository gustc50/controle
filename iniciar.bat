@echo off
REM Inicia o "Controle de Tela por IA" no Windows.
REM Na primeira execucao cria o ambiente virtual e instala as dependencias
REM automaticamente; nas proximas apenas atualiza e abre o programa.

setlocal

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERRO] Python nao foi encontrado no PATH.
    echo Instale o Python 3.10 ou mais recente em https://www.python.org/downloads/
    echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual em .venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Falha ao criar o ambiente virtual.
        pause
        exit /b 1
    )
)

echo Instalando/atualizando dependencias...
".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [ERRO] Falha ao instalar as dependencias. Verifique sua conexao com a internet.
    pause
    exit /b 1
)

echo Iniciando o Controle de Tela por IA...
echo.
".venv\Scripts\python.exe" main.py

if errorlevel 1 (
    echo.
    echo O programa foi encerrado com um erro. Veja as mensagens acima.
    pause
)

endlocal
