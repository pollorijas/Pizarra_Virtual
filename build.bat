@echo off
rem Compila dist\PizarraVirtual.exe en Windows 10/11.
rem Requisitos: Python 3.10 - 3.13 de 64 bits (https://www.python.org/downloads/windows/).
setlocal
cd /d "%~dp0"

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual .venv ...
    %PY% -m venv .venv || goto :error
)
call ".venv\Scripts\activate.bat" || goto :error

python -m pip install --upgrade pip || goto :error
pip install -r requirements.txt -r requirements-dev.txt || goto :error

pyinstaller --noconfirm --clean PizarraVirtual.spec || goto :error

rem Manual de usuario (PDF) y paquete .zip con el ejecutable y el manual
set "QT_QPA_PLATFORM=offscreen"
python tools\build_manual.py --out "dist\Manual de usuario.pdf" || goto :error
set "QT_QPA_PLATFORM="
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\PizarraVirtual.exe','dist\Manual de usuario.pdf' -DestinationPath 'dist\PizarraVirtual.zip'" || goto :error

echo.
echo Listo: %CD%\dist\PizarraVirtual.zip  (PizarraVirtual.exe + Manual de usuario.pdf)
exit /b 0

:error
echo.
echo Se produjo un error durante la compilacion.
exit /b 1
