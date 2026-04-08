@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>nul
cd /d "%~dp0"
set "FORWARDED_ARGS=%*"

echo ================================================================
echo Agent Framework One-Click Start
echo ================================================================
echo.

if exist ".venv\Scripts\python.exe" (
    call :run ".venv\Scripts\python.exe"
    goto :done
)

where py >nul 2>nul
if not errorlevel 1 (
    call :run py
    goto :done
)

where python >nul 2>nul
if not errorlevel 1 (
    call :run python
    goto :done
)

echo [ERROR] Python was not found.
echo Please install Python 3.10+ or create a local .venv first.
set "EXIT_CODE=1"
goto :done

:run
%~1 start_app.py !FORWARDED_ARGS!
set "EXIT_CODE=!ERRORLEVEL!"
goto :eof

:done
if not "!EXIT_CODE!"=="0" (
    echo.
    echo Start failed. Press any key to close this window.
    pause >nul
)
exit /b !EXIT_CODE!
