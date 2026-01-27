"""
ACE Server - Main Entry Point (Fixed SSE)
Implements correct ASGI mounting for MCP integration to avoid Double Response errors.
"""
import sys
import io
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.routing import Route, Mount
from mcp.server.sse import SseServerTransport
from adapters.mcp_server import create_mcp_server
from core.indexer import Indexer
from core.models import IndexRequest

# ---------------------------------------------------------------------
# Windows UTF-8 Fix
# ---------------------------------------------------------------------
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ---------------------------------------------------------------------
# MCP Server & Transport
# ---------------------------------------------------------------------
mcp_server = create_mcp_server()
# We use "/messages/" with a trailing slash to avoid 307 redirects.
sse_transport = SseServerTransport("/messages/")

# ---------------------------------------------------------------------
# FastAPI App Initialization
# ---------------------------------------------------------------------
app = FastAPI(
    title="Antigravity Context Engine (ACE)",
    description="Local Context Server for AI Agents",
    version="1.0.0"
)

# CORS (Allow all for local development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Initialize Indexer
indexer = Indexer()

@app.get("/")
async def root():
    return {"status": "online", "message": "ACE Server is running with Fixed SSE."}

@app.get("/health")
async def health_check():
    print("[DEBUG] Health check hit")
    return {"status": "healthy"}

# ---------------------------------------------------------------------
# MCP Endpoints (The Critical Fix)
# ---------------------------------------------------------------------

@app.get("/sse/")
@app.get("/sse")
async def handle_sse(request: Request):
    """
    SSE Handshake Endpoint.
    """
    print(f"[DEBUG] GET {request.url.path} from {request.client.host}")
    try:
        async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
            print("[DEBUG] SSE Multi-stream established. Entering server.run()")
            await mcp_server.run(
                streams[0], 
                streams[1], 
                mcp_server.create_initialization_options()
            )
    except Exception as e:
        print(f"[ERROR] SSE Loop failure: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("[DEBUG] SSE connection closed")
    return Response(status_code=200)

# CRITICAL FIX REFINED: We use Mount instead of Route.
# Route expects a function that takes `request` and returns `response`.
# Mount expects a raw ASGI application (scope, receive, send).
# Since `sse_transport.handle_post_message` is an ASGI app, we MUST use Mount.
app.router.routes.append(
    Mount(
        "/messages", 
        app=sse_transport.handle_post_message
    )
)

# ---------------------------------------------------------------------
# REST Endpoints (for direct API usage)
# ---------------------------------------------------------------------

@app.post("/v1/context/index")
async def trigger_index(request: IndexRequest):
    try:
        if not os.path.exists(request.project_path):
            return Response(status_code=400, content={"error": "Project path does not exist."})
            
        stats = indexer.index_project(request.project_path, force=request.force)
        return {"status": "success", "stats": stats}
    except Exception as e:
         return Response(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    # Run properly on 0.0.0.0 to be accessible
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
