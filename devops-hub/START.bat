@echo off
cd /d "%~dp0"
where node >nul 2>nul || (echo Node.js not found. Install from https://nodejs.org && pause && exit /b)
node server.js
pause
