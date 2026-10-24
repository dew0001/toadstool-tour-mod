@echo off
title Toadstool Tour Mod
rem Updates the mod if needed, then starts the game in Dolphin.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\play.ps1" %*
if errorlevel 1 (
  echo.
  echo Something went wrong - see the message above.
  pause
)
