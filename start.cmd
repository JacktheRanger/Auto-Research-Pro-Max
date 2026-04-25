@echo off
setlocal
set "ROOT=%~dp0"
pushd "%ROOT%" >nul
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 launcher.py start
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        python launcher.py start
    ) else (
        echo Auto Research Pro Max requires Python 3.11+ on PATH.
        echo Install Python from https://www.python.org/downloads/ and rerun this script.
        pause
        popd >nul
        exit /b 1
    )
)
popd >nul
endlocal
