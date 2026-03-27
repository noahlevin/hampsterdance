"""Hampster Dance AI - Backend Server.

Serves the frontend, REST API, SSE events, and MCP server.
"""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

import database as db
from mcp_server import mcp

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


# ---- SSE Event Bus ----

class EventBus:
    """Simple pub/sub for SSE events."""

    def __init__(self):
        self.subscribers: list[asyncio.Queue] = []

    async def publish(self, event_type: str, data: dict):
        dead = []
        for q in self.subscribers:
            try:
                await q.put({"event": event_type, "data": json.dumps(data)})
            except Exception:
                dead.append(q)
        for q in dead:
            self.subscribers.remove(q)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue):
        if q in self.subscribers:
            self.subscribers.remove(q)


bus = EventBus()


# ---- App ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    # Start the MCP session manager lifecycle
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Hampster Dance AI", lifespan=lifespan)

# CORS — allow any origin for MCP and API access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- REST API ----

@app.get("/api/hamsters")
async def api_list_hamsters():
    return JSONResponse(db.list_hamsters())


@app.get("/api/hamsters/{hamster_id}")
async def api_get_hamster(hamster_id: str):
    hamster = db.get_hamster(hamster_id)
    if not hamster:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    return JSONResponse(hamster)


@app.post("/api/hamsters")
async def api_create_hamster(request: Request):
    body = await request.json()
    name = body.get("name", "").strip()
    creator = body.get("creator", "").strip() or None
    if not name:
        return JSONResponse({"error": "Name is required"}, status_code=400)
    if len(name) > 30:
        return JSONResponse({"error": "Name too long (max 30 chars)"}, status_code=400)

    # Check for duplicate name
    existing = db.get_hamster_by_name(name)
    if existing:
        return JSONResponse({"error": f"A hamster named '{name}' already exists!"}, status_code=409)

    hamster = db.create_hamster(name, creator)
    await bus.publish("hamster_created", hamster)
    return JSONResponse(hamster, status_code=201)


@app.post("/api/hamsters/{hamster_id}/dance")
async def api_dance(hamster_id: str, request: Request):
    body = await request.json()
    style = body.get("style", "default")
    hamster = db.update_hamster_dance(hamster_id, style)
    if not hamster:
        return JSONResponse({"error": "Invalid style or hamster not found"}, status_code=400)
    await bus.publish("hamster_danced", {"hamster_id": hamster_id, "style": style})
    return JSONResponse(hamster)


@app.post("/api/hamsters/{hamster_id}/say")
async def api_say(hamster_id: str, request: Request):
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)
    hamster = db.update_hamster_message(hamster_id, message)
    if not hamster:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    await bus.publish("hamster_said", {"hamster_id": hamster_id, "message": message[:140]})
    return JSONResponse(hamster)


@app.post("/api/hamsters/{hamster_id}/poke/{target_id}")
async def api_poke(hamster_id: str, target_id: str):
    result = db.poke_hamster(hamster_id, target_id)
    if not result:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    poker, target = result
    await bus.publish("hamster_poked", {"poker_id": hamster_id, "target_id": target_id})
    return JSONResponse({"poker": poker, "target": target})


@app.get("/api/hamsters/{hamster_id}/notifications")
async def api_notifications(hamster_id: str):
    notifications = db.get_notifications(hamster_id)
    return JSONResponse(notifications)


@app.get("/api/feed")
async def api_feed(limit: int = 20):
    return JSONResponse(db.get_feed(min(limit, 100)))


@app.post("/api/visit")
async def api_visit():
    count = db.increment_visitors()
    return JSONResponse({"count": count})


# ---- SSE ----

@app.get("/api/events")
async def sse_events(request: Request):
    queue = bus.subscribe()

    async def event_generator():
        try:
            # Send heartbeat every 30s to keep connection alive
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield event
                except asyncio.TimeoutError:
                    yield {"event": "heartbeat", "data": json.dumps({"time": time.time()})}
        except asyncio.CancelledError:
            pass
        finally:
            bus.unsubscribe(queue)

    return EventSourceResponse(event_generator())


# ---- MCP Server ----

# Mount the MCP streamable HTTP app. Its lifespan is managed in our lifespan above.
mcp_app = mcp.streamable_http_app()
# Remove the sub-app's lifespan since we manage it ourselves
mcp_app.router.lifespan_handler = None
app.mount("/mcp", mcp_app)


# ---- Serve Frontend ----
# NOTE: This must be last — it's a catch-all mount.

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
