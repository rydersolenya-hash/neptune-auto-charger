@echo off
setlocal

rem Run the daily recovery script from this project directory.
cd /d "%~dp0"

set "LOG_FILE=%~dp0charge.log"
set "PYTHON312=%LocalAppData%\Programs\Python\Python312\python.exe"

if exist "%PYTHON312%" (
    "%PYTHON312%" -u "%~dp0main.py" >> "%LOG_FILE%" 2>&1
) else (
    py -3 -u "%~dp0main.py" >> "%LOG_FILE%" 2>&1
)

exit /b %ERRORLEVEL%
