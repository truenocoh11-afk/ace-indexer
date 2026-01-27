@echo off
:: Launches the MCP Server Adapter
:: This script is meant to be called by Antigravity or Claude Desktop

cd /d "%~dp0"
call venv\Scripts\activate
python adapters\mcp_server.py
