@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Rode primeiro o iniciar.cmd para preparar o EverLock.
  pause
  exit /b 1
)
echo Cria a copia de seguranca (banco + chave dos rostos). Use uma senha e guarde o arquivo em lugar protegido.
".venv\Scripts\python.exe" -m everlock backup --senha %*
pause
