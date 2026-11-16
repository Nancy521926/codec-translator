@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 goto nopy
for %%f in ("%~dp0*.py") do py -3 "%%~f"
pause
exit /b 0

:nopy
echo Python launcher (py.exe) not found.
echo Please install Python 3 from https://www.python.org/ and try again.
pause
exit /b 1
