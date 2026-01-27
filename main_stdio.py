"""
ACE Server - Stdio Entry Point
Robust transport layer for local IDE integration.
"""
import sys
import asyncio
import io
import os

# Import the MCP SDK components
from mcp.server.stdio import stdio_server
from adapters.mcp_server import create_mcp_server

# ---------------------------------------------------------------------
# Windows UTF-8 Fix
# ---------------------------------------------------------------------
# This prevents crashes when the server tries to print emojis or 
# special characters to a Windows console (cp1252).
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

async def async_main():
    """
    Async logic for the Stdio-based MCP server.
    """
    # Create the MCP server instance (contains tool definitions)
    mcp_server = create_mcp_server()
    
    # Use the stdio_server context manager to handle communication via pipes
    async with stdio_server() as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options()
        )

def main():
    """
    Synchronous entry point for the package script.
    """
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()

