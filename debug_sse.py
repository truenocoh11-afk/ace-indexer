import asyncio
import httpx

async def debug_sse():
    print("🚀 Connecting to raw SSE stream...")
    async with httpx.AsyncClient() as client:
        async with client.stream("GET", "http://127.0.0.1:8000/sse", timeout=10) as response:
            print(f"✅ Connected. Status: {response.status_code}")
            async for line in response.aiter_lines():
                if line.strip():
                    print(f"📨 RX: {line}")
                
                # If we see 'data:', it's likely the endpoint URL
                if line.startswith("data:"):
                    print(f"🎯 ENDPOINT DATA: {line}")
                    break

if __name__ == "__main__":
    asyncio.run(debug_sse())
