@echo off
cd /d "%~dp0"
where pyw >nul 2>nul
if errorlevel 1 goto nopy
for %%f in ("%~dp0*.py") do start "" pyw -3 "%%~f"
exit /b 0

:nopy
echo Python launcher (pyw.exe) not found.
echo Please install Python 3 from https://www.python.org/ and try again.
pause
exit /b 1
