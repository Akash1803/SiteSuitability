@echo off
rem Site Suitability desktop app
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
start "" pythonw -m gui.app
