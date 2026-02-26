"""FastAPI dashboard for monitoring the trading agent."""
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from storage.db import Database

app = FastAPI(title="Polymarket Agent Dashboard")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Shared database instance (set by agent.py)
_db: Database | None = None


def set_database(db: Database):
    global _db
    _db = db


def _get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    db = _get_db()
    summary = await db.get_pnl_summary()
    trades = await db.get_recent_trades(limit=50)
    open_trades = await db.get_open_trades()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "summary": summary,
            "trades": trades,
            "open_trades": open_trades,
        },
    )


@app.get("/api/status")
async def api_status():
    db = _get_db()
    summary = await db.get_pnl_summary()
    open_trades = await db.get_open_trades()
    return {
        "status": "running",
        "pnl": summary,
        "open_positions": len(open_trades),
    }


@app.get("/api/trades")
async def api_trades(limit: int = 50):
    db = _get_db()
    trades = await db.get_recent_trades(limit=limit)
    return {"trades": trades}


@app.get("/api/pnl")
async def api_pnl():
    db = _get_db()
    summary = await db.get_pnl_summary()
    return summary
