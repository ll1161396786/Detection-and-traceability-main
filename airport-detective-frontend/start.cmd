@echo off
cd /d "%~dp0.."
call start-monitor.cmd
if errorlevel 1 pause
