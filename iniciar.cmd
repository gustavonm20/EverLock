@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto no_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)"
if errorlevel 1 goto no_python
if not exist ".venv\Scripts\python.exe" python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\prepare.py
if errorlevel 1 goto failed
echo.
echo EverLock pronto. Abra http://127.0.0.1:8000 no navegador.
echo Se voce configurou EVERLOCK_PORT, use a porta indicada abaixo.
echo Para encerrar, pressione Ctrl+C.
".venv\Scripts\python.exe" -m everlock
if errorlevel 1 goto failed
exit /b 0
:no_python
echo Instale Python 3.13 ou superior e marque a opcao de adiciona-lo ao PATH.
pause
exit /b 1
:failed
echo Nao foi possivel iniciar. Confira o erro acima e as instrucoes do README.
pause
exit /b 1
