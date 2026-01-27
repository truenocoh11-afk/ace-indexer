import asyncio
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

async def main():
    print("[Test] Connecting to ACE via SSE...")
    async with sse_client("http://localhost:8000/sse") as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            
            print("[Test] Connected! Fetching tools...")
            tools = await session.list_tools()
            
            print(f"\n[Test] Found {len(tools.tools)} tools:")
            for tool in tools.tools:
                print(f" - {tool.name}: {tool.description}")
            
            if len(tools.tools) > 0:
                print("\n[Test] SUCCESS: MCP Server is responding via SSE!")
            else:
                print("\n[Test] WARNING: No tools found.")

if __name__ == "__main__":
    asyncio.run(main())
