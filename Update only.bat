@echo off
title Toadstool Tour Mod - update
rem Updates the mod without starting the game (handy right before a NetPlay session).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\play.ps1" -NoLaunch %*
echo.
pause
