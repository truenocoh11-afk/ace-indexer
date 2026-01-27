import asyncio
import httpx
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
import os

async def run_demo():
    print("🚀 Connecting to ACE Server for Index check...")
    
    # Connect to the SSE endpoint
    try:
        async with sse_client("http://127.0.0.1:8000/sse") as (read, write):
            async with ClientSession(read, write) as session:
                print("✅ Session Established.")
                
                # Initialize
                await session.initialize()
                print("🤝 Initialized.")
                
                # Index Project
                project_path = r"c:\Users\Julian\Documents\BoluIdeas\ACE indexer\ace_engine"
                print(f"🔍 Executing Tool: ace_index_project in '{project_path}'...")
                
                result = await session.call_tool("ace_index_project", arguments={"project_path": project_path, "force": False})
                
                print("\n---------- RESULT ----------")
                # The result is a CallToolResult object
                for content in result.content:
                    if content.type == "text":
                        print(content.text)
                print("----------------------------\n")
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_demo())
