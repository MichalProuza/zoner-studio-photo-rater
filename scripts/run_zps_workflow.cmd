@echo off
REM Wrapper pro run_zps_workflow.ps1 — automaticky obchází ExecutionPolicy.
REM Použití: scripts\run_zps_workflow.cmd [parametry]
REM Příklad: scripts\run_zps_workflow.cmd -WriteOnly -DryRun

powershell -ExecutionPolicy Bypass -File "%~dp0run_zps_workflow.ps1" %*
