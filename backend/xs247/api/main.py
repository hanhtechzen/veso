"""Ứng dụng FastAPI. Chạy: uvicorn xs247.api.main:app"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from .. import __version__
from ..collector.context import Ctx, make_http
from ..config import get_settings
from ..db import make_pool
from . import admin, ai, auth, check, contact, errors, forecasts, play, public, stream, tools, track, user
from ..site import routes as site_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.settings = s
    app.state.pool = make_pool(s.database_url, max_size=20)
    await app.state.pool.open(wait=True)
    app.state.redis = Redis.from_url(s.redis_url, decode_responses=True)
    app.state.collector = Ctx(s, app.state.pool, make_http(s))
    yield
    await app.state.collector.http.aclose()
    await app.state.redis.aclose()
    await app.state.pool.close()


app = FastAPI(title="XS247 API", version=__version__, lifespan=lifespan,
              docs_url="/v1/docs", openapi_url="/v1/openapi.json")
errors.install(app)
if get_settings().is_dev:
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])
app.include_router(stream.router)   # đặt trước public để /v1/live/stream không bị hiểu là mã kỳ quay
app.include_router(public.router)
app.include_router(forecasts.router)
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(ai.router)
app.include_router(track.router)
app.include_router(user.router)
app.include_router(play.router)
app.include_router(check.router)
app.include_router(contact.router)
app.include_router(tools.router)
app.include_router(site_routes.router)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    async with app.state.pool.connection() as conn:
        await conn.execute("SELECT 1")
    await app.state.redis.ping()
    return {"ok": True, "version": __version__}
