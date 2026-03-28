"""Hampster Dance AI - Backend Server.

Serves the frontend, REST API, SSE events, and MCP server.
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.base import BaseHTTPMiddleware

import database as db
from mcp_server import mcp

logger = logging.getLogger("hampsterdance")

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


class ActivityLoggingMiddleware(BaseHTTPMiddleware):
    """Log all API POST/DELETE actions and MCP requests for analytics."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path

        # Log API mutations
        if path.startswith("/api/") and request.method in ("POST", "DELETE") and path != "/api/analytics":
            try:
                db.log_analytics(
                    event_type=f"api:{request.method.lower()}",
                    path=path,
                    user_agent=request.headers.get("user-agent"),
                    ip=request.client.host if request.client else None,
                    metadata={"status_code": response.status_code},
                )
            except Exception:
                pass  # never block requests for logging

        # Log MCP requests
        if path.startswith("/mcp") and request.method == "POST":
            try:
                db.log_analytics(
                    event_type="mcp_request",
                    path=path,
                    user_agent=request.headers.get("user-agent"),
                    ip=request.client.host if request.client else None,
                )
            except Exception:
                pass

        return response


app.add_middleware(ActivityLoggingMiddleware)


# ---- REST API ----

@app.get("/api/hamsters/count")
async def api_hamster_count():
    return JSONResponse({"count": db.count_hamsters()})


@app.get("/api/hamsters")
async def api_list_hamsters(page: int = 0, per_page: int = 0, sort: str = "active"):
    # If pagination params provided, use paginated query
    if page > 0 and per_page > 0:
        return JSONResponse(db.list_hamsters_paginated(page, min(per_page, 100), sort))
    # Default: return all (backward compatible)
    return JSONResponse(db.list_hamsters())


@app.get("/api/hamsters/search")
async def api_search_hamsters(q: str = ""):
    if not q.strip():
        return JSONResponse([])
    results = db.search_hamsters(q.strip())
    return JSONResponse(results)


@app.get("/api/hamsters/sleepy")
async def api_sleepy_hamsters():
    sleepy = db.get_sleepy_hamsters()
    return JSONResponse(sleepy)


@app.get("/api/hamsters/by-name/{name:path}")
async def api_get_hamster_by_name(name: str):
    hamster = db.get_hamster_by_name(name)
    if not hamster:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    return JSONResponse(hamster)


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


@app.get("/api/hamsters/{hamster_id}/stats")
async def api_hamster_stats(hamster_id: str):
    stats = db.get_hamster_stats(hamster_id)
    if not stats:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    return JSONResponse(stats)


@app.get("/api/hamsters/{hamster_id}/notifications")
async def api_notifications(hamster_id: str):
    notifications = db.get_notifications(hamster_id)
    return JSONResponse(notifications)


@app.get("/api/hamsters/{hamster_id}/activity")
async def api_hamster_activity(hamster_id: str, limit: int = 50):
    hamster = db.get_hamster(hamster_id)
    if not hamster:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    activity = db.get_hamster_activity(hamster_id, min(limit, 200))
    return JSONResponse(activity)


@app.post("/api/hamsters/{hamster_id}/follow")
async def api_follow_hamster(hamster_id: str, request: Request):
    body = await request.json()
    email = body.get("email", "").strip()
    if not email or "@" not in email or "." not in email:
        return JSONResponse({"error": "Valid email is required"}, status_code=400)
    result = db.add_follower(hamster_id, email)
    if result is None:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    return JSONResponse(result, status_code=201)


@app.get("/api/hamsters/{hamster_id}/followers/count")
async def api_follower_count(hamster_id: str):
    count = db.get_follower_count(hamster_id)
    return JSONResponse({"count": count})


@app.post("/api/hamsters/{hamster_id}/wake")
async def api_wake_hamster(hamster_id: str):
    hamster = db.wake_up_hamster(hamster_id)
    if not hamster:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    await bus.publish("hamster_woke", hamster)
    return JSONResponse(hamster)


@app.get("/api/hamsters/{hamster_id}/horoscope")
async def api_hamster_horoscope(hamster_id: str):
    horoscope = db.get_hamster_horoscope(hamster_id)
    if not horoscope:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    return JSONResponse(horoscope)


@app.get("/api/activity")
async def api_activity(limit: int = 20):
    return JSONResponse(db.get_recent_activity(min(limit, 100)))


@app.get("/api/feed")
async def api_feed(limit: int = 20):
    return JSONResponse(db.get_feed(min(limit, 100)))


@app.post("/api/visit")
async def api_visit():
    count = db.increment_visitors()
    return JSONResponse({"count": count})


# ---- Battles API ----

@app.post("/api/battles")
async def api_create_battle(request: Request):
    body = await request.json()
    challenger_id = body.get("challenger_id", "").strip()
    defender_id = body.get("defender_id", "").strip()
    diss = body.get("diss", "").strip()
    if not challenger_id or not defender_id or not diss:
        return JSONResponse({"error": "challenger_id, defender_id, and diss are required"}, status_code=400)
    if len(diss) > 140:
        return JSONResponse({"error": "Diss too long! Max 140 chars."}, status_code=400)
    if challenger_id == defender_id:
        return JSONResponse({"error": "You can't beef with yourself!"}, status_code=400)
    battle = db.create_battle(challenger_id, defender_id, diss)
    if not battle:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    await bus.publish("battle_started", battle)
    return JSONResponse(battle, status_code=201)


@app.post("/api/battles/{battle_id}/respond")
async def api_respond_battle(battle_id: str, request: Request):
    body = await request.json()
    hamster_id = body.get("hamster_id", "").strip()
    diss = body.get("diss", "").strip()
    if not hamster_id or not diss:
        return JSONResponse({"error": "hamster_id and diss are required"}, status_code=400)
    if len(diss) > 140:
        return JSONResponse({"error": "Diss too long! Max 140 chars."}, status_code=400)
    battle = db.respond_to_battle(battle_id, hamster_id, diss)
    if not battle:
        return JSONResponse({"error": "Battle not found, already responded, or you're not the defender"}, status_code=400)
    await bus.publish("battle_responded", battle)
    return JSONResponse(battle)


@app.post("/api/battles/{battle_id}/cheer")
async def api_cheer_battle(battle_id: str, request: Request):
    body = await request.json()
    side = body.get("side", "").strip()
    if side not in ("challenger", "defender"):
        return JSONResponse({"error": "side must be 'challenger' or 'defender'"}, status_code=400)
    battle = db.cheer_battle(battle_id, side)
    if not battle:
        return JSONResponse({"error": "Battle not found"}, status_code=404)
    await bus.publish("battle_cheered", battle)
    return JSONResponse(battle)


@app.get("/api/battles")
async def api_list_battles(status: str | None = None):
    battles = db.list_battles(status)
    return JSONResponse(battles)


@app.get("/api/battles/{battle_id}")
async def api_get_battle(battle_id: str):
    battle = db.get_battle(battle_id)
    if not battle:
        return JSONResponse({"error": "Battle not found"}, status_code=404)
    return JSONResponse(battle)


# ---- Conga Line API ----

@app.post("/api/conga/join")
async def api_join_conga(request: Request):
    body = await request.json()
    hamster_id = body.get("hamster_id", "").strip()
    if not hamster_id:
        return JSONResponse({"error": "hamster_id is required"}, status_code=400)
    result = db.join_conga(hamster_id)
    if result is None:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    await bus.publish("conga_joined", result)
    return JSONResponse(result)


@app.post("/api/conga/leave")
async def api_leave_conga(request: Request):
    body = await request.json()
    hamster_id = body.get("hamster_id", "").strip()
    if not hamster_id:
        return JSONResponse({"error": "hamster_id is required"}, status_code=400)
    result = db.leave_conga(hamster_id)
    if result is None:
        return JSONResponse({"error": "Hamster not found"}, status_code=404)
    await bus.publish("conga_left", result)
    return JSONResponse(result)


@app.get("/api/conga")
async def api_get_conga():
    return JSONResponse(db.get_conga_line())


@app.delete("/api/conga")
async def api_break_conga():
    result = db.break_conga()
    await bus.publish("conga_left", result)
    return JSONResponse(result)


# ---- Horoscopes API ----

@app.get("/api/horoscopes/today")
async def api_horoscopes_today():
    horoscopes = db.generate_daily_horoscopes()
    return JSONResponse(horoscopes)


@app.get("/api/horoscopes/{sign}")
async def api_horoscope_sign(sign: str):
    horoscope = db.get_horoscope_for_sign(sign.capitalize())
    if not horoscope:
        return JSONResponse({"error": "Horoscope not found for that sign"}, status_code=404)
    return JSONResponse(horoscope)


# ---- Analytics API ----

@app.post("/api/analytics")
async def api_log_analytics(request: Request):
    body = await request.json()
    event_type = body.get("event", "").strip()
    if not event_type:
        return JSONResponse({"error": "event is required"}, status_code=400)
    db.log_analytics(
        event_type=event_type,
        path=body.get("path"),
        referrer=body.get("referrer"),
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
        session_id=body.get("session_id"),
        metadata=body.get("metadata"),
    )
    return JSONResponse({"ok": True})


@app.get("/api/analytics/summary")
async def api_analytics_summary(days: int = 7):
    return JSONResponse(db.get_analytics_summary(min(days, 90)))


@app.get("/api/analytics/events")
async def api_analytics_events(limit: int = 100, event_type: str | None = None):
    return JSONResponse(db.get_analytics_events(min(limit, 500), event_type))


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


# Redirect /mcp to /mcp/ so both work (Starlette mount requires trailing slash)
@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
async def mcp_redirect(request: Request):
    return RedirectResponse(url="/mcp/", status_code=307)


app.mount("/mcp", mcp_app)


# ---- Serve Frontend ----
# NOTE: This must be last — it's a catch-all mount.

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
