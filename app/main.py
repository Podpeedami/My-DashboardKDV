from pathlib import Path
import asyncio
import hashlib
import json
import html
import ipaddress
import mimetypes
import re
import socket
import sqlite3
import urllib.parse
import time
import secrets
import urllib.request
import urllib.error
import uuid
from html.parser import HTMLParser
from typing import Literal
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import base64
from time import perf_counter
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, Response
import httpx
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DB_PATH = DATA_DIR / "dashboard.db"
ICONS_DIR = DATA_DIR / "icons"
BACKGROUNDS_DIR = DATA_DIR / "backgrounds"
TILE_BACKGROUNDS_DIR = DATA_DIR / "tile-backgrounds"
STATIC_DIR = BASE_DIR / "static"

# Embedded-app reverse proxy sessions. The iframe is served from the same
# Dashboard origin so apps that rely on first-party cookies (notably mStream)
# can complete authentication inside the embedded view. Sessions are in-memory
# and expire automatically; the target URL is never persisted to SQLite.
DEFAULT_BACKGROUND_SOURCE = STATIC_DIR / "assets" / "default-background.png"
DEFAULT_BACKGROUND_NAME = "my-dashboardkdv-default.png"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)
BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)
TILE_BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)

APP_TILE_SIZES = {'mini', 'small', 'medium', 'wide', 'tall', 'large', 'xl', 'hero'}


# One-shot discovery of common local web services on the host running Dashboard.
# This is intentionally a manual discovery feature, not continuous status monitoring.
LOCAL_SERVICE_HOST = "host.docker.internal"
LOCAL_SERVICE_CANDIDATES = [
    (80, ("http",), "🌐", "Веб-сервис"),
    (443, ("https",), "🔒", "HTTPS веб-сервис"),
    (3000, ("http",), "🌐", "Веб-сервис на порту 3000"),
    (3001, ("http",), "🌐", "Веб-сервис на порту 3001"),
    (5000, ("http",), "🌐", "Веб-сервис на порту 5000"),
    (5001, ("https", "http"), "🌐", "Веб-сервис на порту 5001"),
    (7000, ("http",), "🌐", "Веб-сервис на порту 7000"),
    (8000, ("http",), "🌐", "Веб-сервис на порту 8000"),
    (8080, ("http",), "🌐", "Веб-сервис на порту 8080"),
    (8081, ("http",), "🌐", "Веб-сервис на порту 8081"),
    (8096, ("http",), "📺", "Emby / Jellyfin"),
    (8097, ("http",), "📺", "Медиа-сервис на порту 8097"),
    (8123, ("http",), "🏠", "Home Assistant"),
    (8181, ("http",), "🌐", "Веб-сервис на порту 8181"),
    (8200, ("http",), "🌐", "Веб-сервис на порту 8200"),
    (8989, ("http",), "📺", "Sonarr"),
    (9000, ("http",), "🐳", "Portainer"),
    (9090, ("http",), "📊", "Prometheus"),
    (32400, ("http",), "🎬", "Plex"),
    (5055, ("http",), "🎬", "Overseerr"),
    (6767, ("http",), "🎬", "Bazarr"),
    (7878, ("http",), "🎬", "Radarr"),
    (8686, ("http",), "🎵", "Lidarr"),
    (9696, ("http",), "🧰", "Prowlarr"),
]

LOCAL_SERVICE_SIGNATURES = (
    (("mstream", "file explorer", "now playing"), "mStream Music", "🎵", "Локальная музыкальная библиотека"),
    (("grafana" ,), "Grafana", "📊", "Мониторинг и графики"),
    (("emby",), "Emby", "📺", "Домашний медиасервер"),
    (("jellyfin",), "Jellyfin", "📺", "Домашний медиасервер"),
    (("portainer",), "Portainer", "🐳", "Управление Docker"),
    (("home assistant",), "Home Assistant", "🏠", "Умный дом"),
    (("sonarr",), "Sonarr", "📺", "Автоматизация сериалов"),
    (("radarr",), "Radarr", "🎬", "Автоматизация фильмов"),
    (("lidarr",), "Lidarr", "🎵", "Автоматизация музыки"),
    (("prowlarr",), "Prowlarr", "🧰", "Менеджер индексаторов"),
    (("bazarr",), "Bazarr", "🎬", "Субтитры для медиасерверов"),
    (("overseerr",), "Overseerr", "🎬", "Запросы медиаконтента"),
    (("plex",), "Plex", "🎬", "Домашний медиасервер"),
    (("prometheus",), "Prometheus", "📊", "Сбор метрик"),
)


def _extract_page_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text or "", flags=re.I | re.S)
    if not match:
        return ""
    value = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip()
    return value[:160]


def _identify_local_service(port: int, title: str, body: str, fallback_name: str, fallback_icon: str, fallback_description: str):
    haystack = f"{title}\n{body[:50000]}".lower()
    for needles, name, icon, description in LOCAL_SERVICE_SIGNATURES:
        if any(needle in haystack for needle in needles):
            return name, icon, description
    return fallback_name, fallback_icon, fallback_description


async def _probe_local_service(client: httpx.AsyncClient, port: int, schemes: tuple[str, ...], icon: str, fallback_name: str):
    for scheme in schemes:
        url = f"{scheme}://{LOCAL_SERVICE_HOST}:{port}/"
        try:
            response = await client.get(
                url,
                headers={"User-Agent": "My DashboardKDV Local Service Discovery/2.9.0"},
                follow_redirects=True,
            )
            content_type = response.headers.get("content-type", "")
            body = response.text[:50000] if "text" in content_type.lower() or "html" in content_type.lower() else ""
            title = _extract_page_title(body)
            name, detected_icon, description = _identify_local_service(
                port, title, body, fallback_name, icon, fallback_name
            )
            final_url = str(response.url).rstrip("/")
            return {
                "port": port,
                "url": final_url,
                "name": name,
                "icon": detected_icon,
                "description": description,
                "title": title,
                "status_code": response.status_code,
            }
        except (httpx.HTTPError, ValueError, UnicodeError):
            continue
    return None
MAX_ICON_BYTES = 5 * 1024 * 1024
MAX_BACKGROUND_BYTES = 8 * 1024 * 1024
ALLOWED_ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}
ALLOWED_BACKGROUND_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
ALLOWED_BACKGROUND_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
ALLOWED_ICON_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}

app = FastAPI(title="My DashboardKDV", version="2.9.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/icons", StaticFiles(directory=ICONS_DIR), name="icons")
app.mount("/backgrounds", StaticFiles(directory=BACKGROUNDS_DIR), name="backgrounds")
app.mount("/tile-backgrounds", StaticFiles(directory=TILE_BACKGROUNDS_DIR), name="tile-backgrounds")

EMBEDDED_SESSION_TTL = 3600
EMBEDDED_SESSION_PATTERN = re.compile(r"^/embedded/([A-Za-z0-9_-]{24,64})(?:/.*)?$")
embedded_sessions: dict[str, dict[str, object]] = {}


def _cleanup_embedded_sessions() -> None:
    now = time.time()
    for session_id, data in list(embedded_sessions.items()):
        if float(data.get("expires_at", 0)) <= now:
            embedded_sessions.pop(session_id, None)


def _normalize_proxy_target(url: str) -> str:
    value = (url or "").strip()
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise HTTPException(400, "URL встроенного приложения должен начинаться с http:// или https://")

    host = parts.hostname or ""
    port = parts.port
    if host in {"localhost", "127.0.0.1"}:
        host = "host.docker.internal"
        authority = host + (f":{port}" if port else "")
        return urlunsplit((parts.scheme, authority, parts.path, parts.query, ""))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def _embedded_session_from_request(request: Request) -> str | None:
    _cleanup_embedded_sessions()
    referer = request.headers.get("referer", "")
    if not referer:
        return None
    try:
        ref_path = urlsplit(referer).path
    except ValueError:
        return None
    match = EMBEDDED_SESSION_PATTERN.match(ref_path)
    if match and match.group(1) in embedded_sessions:
        return match.group(1)
    return None


def _rewrite_location(location: str, session_id: str) -> str:
    if not location:
        return location
    parts = urlsplit(location)
    target = str(embedded_sessions.get(session_id, {}).get("target", ""))
    target_parts = urlsplit(target) if target else None
    if parts.scheme and parts.netloc and target_parts:
        if parts.scheme == target_parts.scheme and parts.netloc == target_parts.netloc:
            path = parts.path or "/"
            return urlunsplit(("", "", f"/embedded/{session_id}{path}", parts.query, parts.fragment))
        return location
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    if path.startswith("/embedded/"):
        return location
    return urlunsplit(("", "", f"/embedded/{session_id}{path}", parts.query, parts.fragment))


def _rewrite_set_cookie(cookie: str) -> str:
    # Store upstream auth cookies on the Dashboard origin. mStream uses the
    # x-access-token cookie for JWT authentication.
    cookie = re.sub(r";\s*Domain=[^;]+", "", cookie, flags=re.I)
    if not re.search(r";\s*Path=", cookie, flags=re.I):
        cookie += "; Path=/"
    return cookie


def _rewrite_forwarded_headers(request: Request, target: str, session_id: str) -> dict[str, str]:
    target_parts = urlsplit(target)
    headers: dict[str, str] = {}
    for name, value in request.headers.items():
        lower = name.lower()
        if lower in {"host", "content-length", "connection", "accept-encoding", "origin", "referer", "sec-fetch-site", "sec-fetch-mode", "sec-fetch-dest"}:
            continue
        headers[name] = value
    # Upstream should see its own origin rather than Dashboard's origin.
    upstream_origin = f"{target_parts.scheme}://{target_parts.netloc}"
    if request.headers.get("origin"):
        headers["origin"] = upstream_origin
    incoming_referer = request.headers.get("referer", "")
    if incoming_referer:
        ref_parts = urlsplit(incoming_referer)
        if ref_parts.path.startswith("/embedded/"):
            prefix = f"/embedded/{session_id}"
            stripped = ref_parts.path[len(prefix):] if ref_parts.path.startswith(prefix) else "/"
            headers["referer"] = urlunsplit((target_parts.scheme, target_parts.netloc, stripped or "/", ref_parts.query, ref_parts.fragment))
        else:
            headers["referer"] = incoming_referer
    headers["x-forwarded-host"] = request.headers.get("host", "")
    headers["x-forwarded-proto"] = request.url.scheme
    return headers


async def _proxy_embedded_request(request: Request, session_id: str, subpath: str = "") -> Response:
    session = embedded_sessions.get(session_id)
    if not session or float(session.get("expires_at", 0)) <= time.time():
        embedded_sessions.pop(session_id, None)
        raise HTTPException(404, "Сессия встроенного приложения истекла")

    target = str(session["target"]).rstrip("/") + "/" + subpath.lstrip("/")
    if request.url.query:
        target += "?" + request.url.query

    body = await request.body()
    forwarded_headers = _rewrite_forwarded_headers(request, target, session_id)

    timeout = httpx.Timeout(60.0, connect=10.0)
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        try:
            upstream = await client.request(request.method, target, headers=forwarded_headers, content=body)
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"Не удалось открыть встроенное приложение: {exc}") from exc

    response = Response(content=upstream.content, status_code=upstream.status_code)
    for name, value in upstream.headers.items():
        lower = name.lower()
        if lower in {"content-length", "transfer-encoding", "connection", "content-encoding", "set-cookie", "location"}:
            continue
        response.headers[name] = value
    for cookie in upstream.headers.get_list("set-cookie"):
        response.headers.append("set-cookie", _rewrite_set_cookie(cookie))
    location = upstream.headers.get("location")
    if location:
        response.headers["location"] = _rewrite_location(location, session_id)
    return response




@app.middleware("http")
async def embedded_proxy_middleware(request: Request, call_next):
    session_id = _embedded_session_from_request(request)
    path = request.url.path
    if session_id and not path.startswith("/embedded/") and not path.startswith("/static/"):
        return await _proxy_embedded_request(request, session_id, path.lstrip("/"))
    return await call_next(request)


@app.post("/api/embedded/session")
async def create_embedded_session(request: Request):
    payload = await request.json()
    target = _normalize_proxy_target(str(payload.get("url", "")))
    _cleanup_embedded_sessions()
    session_id = secrets.token_urlsafe(24)
    embedded_sessions[session_id] = {"target": target, "expires_at": time.time() + EMBEDDED_SESSION_TTL}
    return {"id": session_id, "url": f"/embedded/{session_id}/"}


@app.api_route("/embedded/{session_id}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@app.api_route("/embedded/{session_id}/", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def embedded_entry(request: Request, session_id: str):
    return await _proxy_embedded_request(request, session_id, "")


@app.api_route("/embedded/{session_id}/{subpath:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def embedded_prefixed_proxy(request: Request, session_id: str, subpath: str):
    return await _proxy_embedded_request(request, session_id, subpath)




class Category(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    icon: str = Field(default="📁", max_length=500)


class AppItem(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=300)
    category_id: int
    icon: str = Field(default="🚀", max_length=500)
    favorite: bool = False
    open_mode: Literal['external', 'embedded'] = 'external'
    size: Literal['mini', 'small', 'medium', 'wide', 'tall', 'large', 'xl', 'hero'] = 'medium'
    status_enabled: bool = True
    tile_bg_mode: Literal['default', 'color', 'image'] = 'default'
    tile_bg_value: str = Field(default="", max_length=2048)
    tile_bg_scale: int = Field(default=100, ge=50, le=200)
    tile_opacity: float = Field(default=0.90, ge=0.45, le=1.0)
    tile_blur: float = Field(default=6.0, ge=0.0, le=20.0)
    tile_icon_size: int = Field(default=48, ge=24, le=96)
    tile_title_size: int = Field(default=17, ge=12, le=28)
    tile_title_color: str = Field(default='#ffffff', pattern=r'^#[0-9a-fA-F]{6}$')
    tile_description_color: str = Field(default='#cbd5e1', pattern=r'^#[0-9a-fA-F]{6}$')
    tile_url_color: str = Field(default='#94a3b8', pattern=r'^#[0-9a-fA-F]{6}$')
    tile_show_description: bool = True
    tile_show_url: bool = False


class ExportCategory(BaseModel):
    id: int
    name: str = Field(min_length=1, max_length=100)
    icon: str = Field(default="📁", max_length=500)
    sort_order: int = 0


class ExportApp(BaseModel):
    id: int
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=300)
    category_id: int
    icon: str = Field(default="🚀", max_length=500)
    favorite: bool = False
    open_mode: Literal['external', 'embedded'] = 'external'
    size: Literal['mini', 'small', 'medium', 'wide', 'tall', 'large', 'xl', 'hero'] = 'medium'
    status_enabled: bool = True
    tile_bg_mode: Literal['default', 'color', 'image'] = 'default'
    tile_bg_value: str = Field(default="", max_length=2048)
    tile_bg_scale: int = Field(default=100, ge=50, le=200)
    tile_opacity: float = Field(default=0.90, ge=0.45, le=1.0)
    tile_blur: float = Field(default=6.0, ge=0.0, le=20.0)
    tile_icon_size: int = Field(default=48, ge=24, le=96)
    tile_title_size: int = Field(default=17, ge=12, le=28)
    tile_title_color: str = Field(default='#ffffff', pattern=r'^#[0-9a-fA-F]{6}$')
    tile_description_color: str = Field(default='#cbd5e1', pattern=r'^#[0-9a-fA-F]{6}$')
    tile_url_color: str = Field(default='#94a3b8', pattern=r'^#[0-9a-fA-F]{6}$')
    tile_show_description: bool = True
    tile_show_url: bool = False
    sort_order: int = 0


class ReorderApps(BaseModel):
    ids: list[int] = Field(default_factory=list)


class DashboardSettings(BaseModel):
    version: int = 1
    app_name: str = "My DashboardKDV"
    theme: str = "dark"
    categories: list[ExportCategory] = Field(default_factory=list)
    apps: list[ExportApp] = Field(default_factory=list)
    emby: dict = Field(default_factory=dict)
    background: dict = Field(default_factory=dict)
    appearance: dict = Field(default_factory=dict)
    assets: list[dict] = Field(default_factory=list)
    preferences: dict = Field(default_factory=dict)


class EmbyConfig(BaseModel):
    name: str = Field(default="Emby", max_length=100)
    url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=500)
    enabled: bool = True


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as conn:
        conn.execute("DROP TABLE IF EXISTS servers")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            icon TEXT NOT NULL DEFAULT '📁',
            sort_order INTEGER NOT NULL DEFAULT 0)"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', category_id INTEGER NOT NULL,
            icon TEXT NOT NULL DEFAULT '🚀', favorite INTEGER NOT NULL DEFAULT 0,
            open_mode TEXT NOT NULL DEFAULT 'external',
            size TEXT NOT NULL DEFAULT 'medium',
            status_enabled INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON UPDATE CASCADE ON DELETE RESTRICT)"""
        )
        category_columns = {row['name'] for row in conn.execute("PRAGMA table_info(categories)").fetchall()}
        if 'sort_order' not in category_columns:
            conn.execute("ALTER TABLE categories ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        if conn.execute("SELECT COUNT(*) FROM categories WHERE sort_order != 0").fetchone()[0] == 0:
            conn.execute("UPDATE categories SET sort_order = id - 1")

        app_columns = {row['name'] for row in conn.execute("PRAGMA table_info(apps)").fetchall()}
        added_tile_icon_size = False
        added_tile_title_size = False
        if 'open_mode' not in app_columns:
            conn.execute("ALTER TABLE apps ADD COLUMN open_mode TEXT NOT NULL DEFAULT 'external'")
        if 'size' not in app_columns:
            conn.execute("ALTER TABLE apps ADD COLUMN size TEXT NOT NULL DEFAULT 'medium'")
        if 'status_enabled' not in app_columns:
            conn.execute("ALTER TABLE apps ADD COLUMN status_enabled INTEGER NOT NULL DEFAULT 1")
        if 'sort_order' not in app_columns:
            conn.execute("ALTER TABLE apps ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        for column_sql in [
            "ALTER TABLE apps ADD COLUMN tile_bg_mode TEXT NOT NULL DEFAULT 'default'",
            "ALTER TABLE apps ADD COLUMN tile_bg_value TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE apps ADD COLUMN tile_bg_scale INTEGER NOT NULL DEFAULT 100",
            "ALTER TABLE apps ADD COLUMN tile_opacity REAL NOT NULL DEFAULT 0.90",
            "ALTER TABLE apps ADD COLUMN tile_blur REAL NOT NULL DEFAULT 6.0",
            "ALTER TABLE apps ADD COLUMN tile_icon_size INTEGER NOT NULL DEFAULT 48",
            "ALTER TABLE apps ADD COLUMN tile_title_size INTEGER NOT NULL DEFAULT 17",
            "ALTER TABLE apps ADD COLUMN tile_title_color TEXT NOT NULL DEFAULT '#ffffff'",
            "ALTER TABLE apps ADD COLUMN tile_description_color TEXT NOT NULL DEFAULT '#cbd5e1'",
            "ALTER TABLE apps ADD COLUMN tile_url_color TEXT NOT NULL DEFAULT '#94a3b8'",
            "ALTER TABLE apps ADD COLUMN tile_show_description INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE apps ADD COLUMN tile_show_url INTEGER NOT NULL DEFAULT 0",
        ]:
            column_name = column_sql.split('ADD COLUMN ', 1)[1].split()[0]
            if column_name not in app_columns:
                conn.execute(column_sql)
                app_columns.add(column_name)
                if column_name == 'tile_icon_size':
                    added_tile_icon_size = True
                if column_name == 'tile_title_size':
                    added_tile_title_size = True
        conn.execute("UPDATE apps SET open_mode='external' WHERE open_mode NOT IN ('external','embedded') OR open_mode IS NULL")
        conn.execute("UPDATE apps SET status_enabled=1 WHERE status_enabled IS NULL")
        conn.execute("UPDATE apps SET size='medium' WHERE size NOT IN ('mini','small','medium','wide','tall','large','xl','hero') OR size IS NULL")
        conn.execute("UPDATE apps SET tile_bg_mode='default' WHERE tile_bg_mode NOT IN ('default','color','image') OR tile_bg_mode IS NULL")
        conn.execute("UPDATE apps SET tile_bg_value='' WHERE tile_bg_value IS NULL")
        conn.execute("UPDATE apps SET tile_bg_scale=100 WHERE tile_bg_scale IS NULL OR tile_bg_scale < 50 OR tile_bg_scale > 200")
        conn.execute("UPDATE apps SET tile_opacity=0.90 WHERE tile_opacity IS NULL OR tile_opacity < 0.45 OR tile_opacity > 1.0")
        conn.execute("UPDATE apps SET tile_blur=6.0 WHERE tile_blur IS NULL OR tile_blur < 0 OR tile_blur > 20")
        conn.execute("UPDATE apps SET tile_icon_size=48 WHERE tile_icon_size IS NULL OR tile_icon_size < 24 OR tile_icon_size > 96")
        conn.execute("UPDATE apps SET tile_title_size=17 WHERE tile_title_size IS NULL OR tile_title_size < 12 OR tile_title_size > 28")
        for col, default in (("tile_title_color", "#ffffff"), ("tile_description_color", "#cbd5e1"), ("tile_url_color", "#94a3b8")):
            conn.execute(f"UPDATE apps SET {col}=? WHERE {col} IS NULL OR {col} NOT GLOB '#??????'", (default,))
        if added_tile_icon_size:
            conn.execute("UPDATE apps SET tile_icon_size = CASE size WHEN 'mini' THEN 36 WHEN 'small' THEN 40 WHEN 'large' THEN 60 WHEN 'xl' THEN 72 WHEN 'hero' THEN 72 ELSE 48 END")
        if added_tile_title_size:
            conn.execute("UPDATE apps SET tile_title_size = CASE size WHEN 'small' THEN 15 WHEN 'large' THEN 19 WHEN 'xl' THEN 21 WHEN 'hero' THEN 21 ELSE 17 END")
        if conn.execute("SELECT COUNT(*) FROM apps WHERE sort_order != 0").fetchone()[0] == 0:
            conn.execute("UPDATE apps SET sort_order = id - 1")

        conn.execute(
            """CREATE TABLE IF NOT EXISTS background_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            path TEXT NOT NULL DEFAULT '',
            opacity REAL NOT NULL DEFAULT 0.35,
            enabled INTEGER NOT NULL DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS emby_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT NOT NULL DEFAULT 'Emby',
            url TEXT NOT NULL DEFAULT '',
            api_key TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS appearance_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            card_opacity REAL NOT NULL DEFAULT 0.90,
            card_blur REAL NOT NULL DEFAULT 6.0,
            background_blur REAL NOT NULL DEFAULT 2.0,
            background_dim REAL NOT NULL DEFAULT 0.55,
            status_checks_enabled INTEGER NOT NULL DEFAULT 1
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS dashboard_preferences (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            theme TEXT NOT NULL DEFAULT 'dark'
            )"""
        )
        if conn.execute("SELECT 1 FROM dashboard_preferences WHERE id=1").fetchone() is None:
            conn.execute("INSERT INTO dashboard_preferences(id,theme) VALUES(1,'dark')")
        conn.execute("UPDATE dashboard_preferences SET theme='dark' WHERE theme NOT IN ('dark','light') OR theme IS NULL")
        appearance_columns = {row['name'] for row in conn.execute("PRAGMA table_info(appearance_settings)").fetchall()}
        if 'status_checks_enabled' not in appearance_columns:
            conn.execute("ALTER TABLE appearance_settings ADD COLUMN status_checks_enabled INTEGER NOT NULL DEFAULT 1")
        if conn.execute("SELECT 1 FROM appearance_settings WHERE id=1").fetchone() is None:
            conn.execute(
                "INSERT INTO appearance_settings(id,card_opacity,card_blur,background_blur,background_dim,status_checks_enabled) VALUES(1,0.90,6.0,2.0,0.55,1)"
            )
        conn.execute("UPDATE background_settings SET opacity=1 WHERE id=1")
        background_row = conn.execute("SELECT id FROM background_settings WHERE id=1").fetchone()
        if background_row is None and DEFAULT_BACKGROUND_SOURCE.exists():
            default_path = BACKGROUNDS_DIR / DEFAULT_BACKGROUND_NAME
            if not default_path.exists():
                default_path.write_bytes(DEFAULT_BACKGROUND_SOURCE.read_bytes())
            conn.execute(
                "INSERT INTO background_settings(id,path,opacity,enabled) VALUES(1,?,?,1)",
                (f"/backgrounds/{DEFAULT_BACKGROUND_NAME}", 1.0),
            )
        if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO categories(name, icon, sort_order) VALUES (?, ?, ?)",
                [("Мои приложения", "🚀", 0), ("Инструменты", "🛠️", 1), ("Мониторинг", "📊", 2), ("Docker", "🐳", 3)],
            )
        if conn.execute("SELECT COUNT(*) FROM apps").fetchone()[0] == 0:
            cat = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM categories")}
            conn.executemany(
                """INSERT INTO apps
                (name,url,description,category_id,icon,favorite,size,status_enabled,sort_order) VALUES (?,?,?,?,?,?,?,?,?)""",
                [
                    ("Video Converter", "http://localhost:8000", "Перекодировка видео", cat["Мои приложения"], "🎬", 1, "medium", 1, 0),
                    ("GitHub", "https://github.com/", "Репозитории и код", cat["Инструменты"], "💻", 1, "medium", 1, 1),
                    ("Docker", "https://www.docker.com/", "Контейнеры и образы", cat["Docker"], "🐳", 1, "medium", 1, 2),
                ],
            )


@app.on_event("startup")
def startup():
    init_db()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/categories")
def categories():
    with db() as conn:
        rows = conn.execute(
            """SELECT c.id,c.name,c.icon,c.sort_order,COUNT(a.id) AS app_count FROM categories c
            LEFT JOIN apps a ON a.category_id=c.id GROUP BY c.id ORDER BY c.sort_order,c.id"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/categories")
def create_category(item: Category):
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO categories(name,icon,sort_order) VALUES (?,?,?)", (item.name.strip(), item.icon.strip() or "📁", int(conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM categories").fetchone()["next_order"]))
            )
            return {"id": cur.lastrowid, **item.model_dump()}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Такая категория уже существует")


@app.put("/api/categories/{category_id}")
def update_category(category_id: int, item: Category):
    try:
        with db() as conn:
            cur = conn.execute(
                "UPDATE categories SET name=?,icon=? WHERE id=?",
                (item.name.strip(), item.icon.strip() or "📁", category_id),
            )
            if not cur.rowcount:
                raise HTTPException(404, "Категория не найдена")
            return {"id": category_id, **item.model_dump()}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Такая категория уже существует")


@app.delete("/api/categories/{category_id}")
def delete_category(category_id: int):
    with db() as conn:
        if conn.execute("SELECT COUNT(*) FROM apps WHERE category_id=?", (category_id,)).fetchone()[0]:
            raise HTTPException(409, "Нельзя удалить категорию, в которой есть приложения")
        if not conn.execute("DELETE FROM categories WHERE id=?", (category_id,)).rowcount:
            raise HTTPException(404, "Категория не найдена")
    return {"ok": True}


class ReorderCategories(BaseModel):
    ids: list[int] = Field(default_factory=list)


@app.post("/api/categories/reorder")
def reorder_categories(payload: ReorderCategories):
    incoming = [int(x) for x in payload.ids]
    with db() as conn:
        rows = conn.execute("SELECT id FROM categories ORDER BY sort_order,id").fetchall()
        current_ids = [int(r["id"]) for r in rows]
        if len(incoming) != len(current_ids) or set(incoming) != set(current_ids):
            raise HTTPException(400, "Список категорий для сортировки не совпадает с текущим списком")
        conn.executemany("UPDATE categories SET sort_order=? WHERE id=?", [(position, category_id) for position, category_id in enumerate(incoming)])
    return {"ok": True, "count": len(incoming)}



@app.get("/api/local-services/discover")
async def discover_local_services():
    """Find common HTTP services listening on the Docker host.

    The endpoint performs a one-shot scan of a small curated list of web ports.
    It does not save anything and does not run periodically.
    """
    async with httpx.AsyncClient(timeout=httpx.Timeout(1.8, connect=0.7), verify=False) as client:
        tasks = [
            _probe_local_service(client, port, schemes, icon, fallback_name)
            for port, schemes, icon, fallback_name in LOCAL_SERVICE_CANDIDATES
        ]
        results = await asyncio.gather(*tasks)
    services = [item for item in results if item]
    services.sort(key=lambda item: (item["port"], item["name"].lower()))
    return {"host": LOCAL_SERVICE_HOST, "services": services, "count": len(services)}


@app.get("/api/apps")
def list_apps():
    with db() as conn:
        rows = conn.execute(
            """SELECT a.id,a.name,a.url,a.description,a.category_id,a.icon,a.favorite,a.open_mode,a.size,a.status_enabled,a.sort_order,
            a.tile_bg_mode,a.tile_bg_value,a.tile_bg_scale,a.tile_opacity,a.tile_blur,a.tile_icon_size,a.tile_title_size,
            a.tile_title_color,a.tile_description_color,a.tile_url_color,
            a.tile_show_description,a.tile_show_url,
            c.name AS category_name,c.icon AS category_icon FROM apps a JOIN categories c ON c.id=a.category_id
            ORDER BY a.sort_order,a.id"""
        ).fetchall()
    return [dict(r) | {"favorite": bool(r["favorite"])} for r in rows]


@app.post("/api/apps/reorder")
def reorder_apps(payload: ReorderApps):
    incoming = payload.ids
    with db() as conn:
        rows = conn.execute("SELECT id FROM apps ORDER BY sort_order,id").fetchall()
        current_ids = [int(r["id"]) for r in rows]
        if len(incoming) != len(current_ids) or set(incoming) != set(current_ids):
            raise HTTPException(400, "Список приложений для сортировки не совпадает с текущим списком")
        conn.executemany(
            "UPDATE apps SET sort_order=? WHERE id=?",
            [(position, app_id) for position, app_id in enumerate(incoming)],
        )
    return {"ok": True, "count": len(incoming)}


@app.post("/api/apps")
def create_app(item: AppItem):
    with db() as conn:
        if not conn.execute("SELECT id FROM categories WHERE id=?", (item.category_id,)).fetchone():
            raise HTTPException(400, "Категория не найдена")
        next_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM apps").fetchone()["next_order"]
        cur = conn.execute(
            """INSERT INTO apps(name,url,description,category_id,icon,favorite,open_mode,size,status_enabled,sort_order,
            tile_bg_mode,tile_bg_value,tile_bg_scale,tile_opacity,tile_blur,tile_icon_size,tile_title_size,tile_title_color,tile_description_color,tile_url_color,tile_show_description,tile_show_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item.name.strip(), item.url.strip(), item.description.strip(), item.category_id, item.icon.strip() or "🚀", int(item.favorite), item.open_mode,
             item.size, int(item.status_enabled), int(next_order), item.tile_bg_mode, item.tile_bg_value.strip(), item.tile_bg_scale, item.tile_opacity,
             item.tile_blur, item.tile_icon_size, item.tile_title_size, item.tile_title_color, item.tile_description_color, item.tile_url_color, int(item.tile_show_description), int(item.tile_show_url)),
        )
        return {"id": cur.lastrowid, **item.model_dump()}


@app.put("/api/apps/{app_id}")
def update_app(app_id: int, item: AppItem):
    with db() as conn:
        if not conn.execute("SELECT id FROM categories WHERE id=?", (item.category_id,)).fetchone():
            raise HTTPException(400, "Категория не найдена")
        cur = conn.execute(
            """UPDATE apps SET name=?,url=?,description=?,category_id=?,icon=?,favorite=?,open_mode=?,size=?,status_enabled=?,
            tile_bg_mode=?,tile_bg_value=?,tile_bg_scale=?,tile_opacity=?,tile_blur=?,tile_icon_size=?,tile_title_size=?,tile_title_color=?,tile_description_color=?,tile_url_color=?,tile_show_description=?,tile_show_url=?
            WHERE id=?""",
            (item.name.strip(), item.url.strip(), item.description.strip(), item.category_id, item.icon.strip() or "🚀", int(item.favorite), item.open_mode,
             item.size, int(item.status_enabled), item.tile_bg_mode, item.tile_bg_value.strip(), item.tile_bg_scale, item.tile_opacity, item.tile_blur,
             item.tile_icon_size, item.tile_title_size, item.tile_title_color, item.tile_description_color, item.tile_url_color, int(item.tile_show_description), int(item.tile_show_url), app_id),
        )
        if not cur.rowcount:
            raise HTTPException(404, "Приложение не найдено")
    return {"id": app_id, **item.model_dump()}


@app.post("/api/apps/{app_id}/duplicate")
def duplicate_app(app_id: int):
    with db() as conn:
        row = conn.execute(
            """SELECT name,url,description,category_id,icon,favorite,open_mode,size,status_enabled,
            tile_bg_mode,tile_bg_value,tile_bg_scale,tile_opacity,tile_blur,tile_icon_size,tile_title_size,tile_title_color,tile_description_color,tile_url_color,tile_show_description,tile_show_url
            FROM apps WHERE id=?""",
            (app_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Приложение не найдено")
        next_order = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM apps").fetchone()["next_order"]
        cur = conn.execute(
            """INSERT INTO apps(name,url,description,category_id,icon,favorite,open_mode,size,status_enabled,sort_order,
            tile_bg_mode,tile_bg_value,tile_bg_scale,tile_opacity,tile_blur,tile_icon_size,tile_title_size,tile_title_color,tile_description_color,tile_url_color,tile_show_description,tile_show_url)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (f"{row['name']} (копия)", row["url"], row["description"], row["category_id"], row["icon"], row["favorite"], row["open_mode"], row["size"], row["status_enabled"], int(next_order),
             row["tile_bg_mode"], row["tile_bg_value"], row["tile_bg_scale"], row["tile_opacity"], row["tile_blur"], row["tile_icon_size"], row["tile_title_size"], row["tile_title_color"], row["tile_description_color"], row["tile_url_color"], row["tile_show_description"], row["tile_show_url"]),
        )
    return {"id": cur.lastrowid}


@app.delete("/api/apps/{app_id}")
def delete_app(app_id: int):
    with db() as conn:
        if not conn.execute("DELETE FROM apps WHERE id=?", (app_id,)).rowcount:
            raise HTTPException(404, "Приложение не найдено")
    return {"ok": True}


# ---------------- Application status ----------------
def _status_is_allowed_host(hostname: str) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        addresses = {item[4][0] for item in infos}
        for raw in addresses:
            ip = ipaddress.ip_address(raw)
            if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                return False
            # Block cloud metadata and other special link-local ranges, while allowing normal LAN services.
            if str(ip) in {"169.254.169.254", "100.100.100.200"}:
                return False
        return bool(addresses)
    except (socket.gaierror, ValueError):
        return False


def _check_app_status(app_item: dict) -> dict:
    app_id = int(app_item["id"])
    url = str(app_item.get("url") or "").strip()
    if not app_item.get("status_enabled", 1):
        return {"id": app_id, "state": "disabled", "online": None, "code": None, "latency_ms": None, "checked_at": None, "message": "Проверка выключена"}
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return {"id": app_id, "state": "unsupported", "online": None, "code": None, "latency_ms": None, "checked_at": None, "message": "Только HTTP/HTTPS"}
    if not _status_is_allowed_host(parsed.hostname):
        return {"id": app_id, "state": "unsupported", "online": None, "code": None, "latency_ms": None, "checked_at": None, "message": "Локальный/служебный адрес не проверяется"}
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "My-DashboardKDV/2.0",
            "Accept": "text/html,application/json,*/*;q=0.8",
            "Range": "bytes=0-0",
        },
        method="GET",
    )
    started = perf_counter()
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        with urllib.request.urlopen(req, timeout=4, allow_redirects=True) as resp:
            resp.read(1)
            elapsed = round((perf_counter() - started) * 1000)
            code = int(resp.status)
            state = "online" if code < 500 else "degraded"
            return {"id": app_id, "state": state, "online": True, "code": code, "latency_ms": elapsed, "checked_at": checked_at, "message": resp.reason or "OK"}
    except urllib.error.HTTPError as exc:
        elapsed = round((perf_counter() - started) * 1000)
        code = int(exc.code)
        state = "online" if code < 500 else "degraded"
        return {"id": app_id, "state": state, "online": True, "code": code, "latency_ms": elapsed, "checked_at": checked_at, "message": str(exc.reason or "HTTP error")}
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as exc:
        elapsed = round((perf_counter() - started) * 1000)
        return {"id": app_id, "state": "offline", "online": False, "code": None, "latency_ms": elapsed, "checked_at": checked_at, "message": str(exc.reason if isinstance(exc, urllib.error.URLError) and getattr(exc, "reason", None) else exc)[:180]}
    except Exception as exc:
        elapsed = round((perf_counter() - started) * 1000)
        return {"id": app_id, "state": "offline", "online": False, "code": None, "latency_ms": elapsed, "checked_at": checked_at, "message": str(exc)[:180]}


@app.get("/api/apps/status")
def app_statuses():
    with db() as conn:
        appearance = conn.execute("SELECT status_checks_enabled FROM appearance_settings WHERE id=1").fetchone()
        if appearance is not None and not bool(appearance["status_checks_enabled"]):
            rows = conn.execute("SELECT id FROM apps ORDER BY sort_order,id").fetchall()
            return [{"id": int(row["id"]), "state": "disabled_global", "online": None, "code": None, "latency_ms": None, "checked_at": None, "message": "Проверка статусов отключена в настройках панели"} for row in rows]
        rows = conn.execute("SELECT id,url,status_enabled FROM apps ORDER BY sort_order,id").fetchall()
    result = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(rows)))) as pool:
        futures = [pool.submit(_check_app_status, dict(row)) for row in rows]
        for future in as_completed(futures):
            result.append(future.result())
    return sorted(result, key=lambda item: item["id"])


def _safe_extension(filename: str, content_type: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in ALLOWED_ICON_EXTENSIONS:
        return ".jpg" if ext == ".jpeg" else ext
    return ALLOWED_ICON_MIME.get((content_type or "").split(";")[0].lower(), "")


def _save_icon_bytes(data: bytes, ext: str) -> str:
    if not data:
        raise HTTPException(400, "Файл иконки пустой")
    if len(data) > MAX_ICON_BYTES:
        raise HTTPException(413, "Иконка слишком большая. Максимум 5 МБ")
    if ext not in ALLOWED_ICON_EXTENSIONS:
        raise HTTPException(400, "Поддерживаются PNG, JPG, WEBP, GIF и ICO")
    name = f"{uuid.uuid4().hex}{ext}"
    path = ICONS_DIR / name
    path.write_bytes(data)
    return f"/icons/{name}"


def _safe_background_extension(filename: str, content_type: str | None) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext in ALLOWED_BACKGROUND_EXTENSIONS:
        return ".jpg" if ext == ".jpeg" else ext
    return ALLOWED_BACKGROUND_MIME.get((content_type or "").split(";")[0].lower(), "")


def _save_background_bytes(data: bytes, ext: str) -> str:
    if not data:
        raise HTTPException(400, "Фоновое изображение пустое")
    if len(data) > MAX_BACKGROUND_BYTES:
        raise HTTPException(413, "Фоновое изображение слишком большое. Максимум 8 МБ")
    if ext not in ALLOWED_BACKGROUND_EXTENSIONS:
        raise HTTPException(400, "Поддерживаются PNG, JPG, WEBP и GIF")
    name = f"{uuid.uuid4().hex}{ext}"
    path = BACKGROUNDS_DIR / name
    path.write_bytes(data)
    rel = f"/backgrounds/{name}"
    with db() as conn:
        conn.execute(
            """INSERT INTO background_settings(id,path,opacity,enabled) VALUES(1,?,1.0,1)
            ON CONFLICT(id) DO UPDATE SET path=excluded.path,enabled=1""",
            (rel,),
        )
    return rel


def _save_tile_background_bytes(data: bytes, ext: str) -> str:
    """Save an application-tile background separately from the global dashboard background."""
    if not data:
        raise HTTPException(400, "Фоновое изображение плитки пустое")
    if len(data) > MAX_BACKGROUND_BYTES:
        raise HTTPException(413, "Фоновое изображение плитки слишком большое. Максимум 8 МБ")
    if ext not in ALLOWED_BACKGROUND_EXTENSIONS:
        raise HTTPException(400, "Поддерживаются PNG, JPG, WEBP и GIF")
    name = f"{uuid.uuid4().hex}{ext}"
    path = TILE_BACKGROUNDS_DIR / name
    path.write_bytes(data)
    return f"/api/tile-background/{name}"


def _appearance_settings() -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT card_opacity,card_blur,background_blur,background_dim,status_checks_enabled FROM appearance_settings WHERE id=1"
        ).fetchone()
    if not row:
        return {"card_opacity": 0.90, "card_blur": 6.0, "background_blur": 2.0, "background_dim": 0.55, "status_checks_enabled": True}
    return {
        "card_opacity": max(0.45, min(1.0, float(row["card_opacity"] or 0.90))),
        "card_blur": max(0.0, min(20.0, float(row["card_blur"] or 6.0))),
        "background_blur": max(0.0, min(12.0, float(row["background_blur"] or 2.0))),
        "background_dim": max(0.0, min(0.85, float(row["background_dim"] or 0.55))),
        "status_checks_enabled": bool(row["status_checks_enabled"]),
    }


@app.get("/api/appearance")
def get_appearance():
    return _appearance_settings()


@app.put("/api/appearance")
def update_appearance(payload: dict):
    try:
        card_opacity = float(payload.get("card_opacity", 0.90))
        card_blur = float(payload.get("card_blur", 6.0))
        background_blur = float(payload.get("background_blur", 2.0))
        background_dim = float(payload.get("background_dim", 0.55))
        status_checks_enabled = bool(payload.get("status_checks_enabled", True))
    except (TypeError, ValueError):
        raise HTTPException(400, "Некорректные значения внешнего вида")
    if not 0.45 <= card_opacity <= 1.0:
        raise HTTPException(400, "Прозрачность плиток должна быть от 45 до 100%")
    if not 0 <= card_blur <= 20:
        raise HTTPException(400, "Размытие плиток должно быть от 0 до 20 px")
    if not 0 <= background_blur <= 12:
        raise HTTPException(400, "Размытие фона должно быть от 0 до 12 px")
    if not 0 <= background_dim <= 0.85:
        raise HTTPException(400, "Затемнение фона должно быть от 0 до 85%")
    with db() as conn:
        conn.execute(
            """INSERT INTO appearance_settings(id,card_opacity,card_blur,background_blur,background_dim,status_checks_enabled) VALUES(1,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET card_opacity=excluded.card_opacity,card_blur=excluded.card_blur,background_blur=excluded.background_blur,background_dim=excluded.background_dim,status_checks_enabled=excluded.status_checks_enabled""",
            (card_opacity, card_blur, background_blur, background_dim, int(status_checks_enabled)),
        )
    return _appearance_settings()


def _background_settings() -> dict:
    with db() as conn:
        row = conn.execute("SELECT path,opacity,enabled FROM background_settings WHERE id=1").fetchone()
    if not row:
        return {"enabled": False, "url": "", "opacity": 1.0}
    return {
        "enabled": bool(row["enabled"] and row["path"]),
        "url": row["path"],
        "opacity": 1.0,
    }


def _background_file_for_export() -> Path | None:
    with db() as conn:
        row = conn.execute("SELECT path FROM background_settings WHERE id=1").fetchone()
    if not row or not row["path"]:
        return None
    value = str(row["path"])
    if not value.startswith("/backgrounds/"):
        return None
    name = Path(value.removeprefix("/backgrounds/")).name
    if not name:
        return None
    path = BACKGROUNDS_DIR / name
    return path if path.exists() and path.is_file() else None


def _host_is_public(host: str) -> bool:
    host = host.strip().lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        addresses = {item[4][0] for item in infos}
        if not addresses:
            return False
        for raw in addresses:
            ip = ipaddress.ip_address(raw)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                return False
        return True
    except (socket.gaierror, ValueError):
        return False


def _download_image(url: str) -> tuple[bytes, str]:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "Разрешены только HTTP и HTTPS ссылки")
    if len(url) > 2048:
        raise HTTPException(400, "Ссылка слишком длинная")
    if not _host_is_public(parsed.hostname):
        raise HTTPException(400, "Ссылка ведёт на локальный или недоступный адрес")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "My-DashboardKDV/4.2", "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0].lower()
            if content_type.startswith("text/") or content_type in {"application/json", "application/javascript"}:
                raise HTTPException(400, "Ссылка не ведёт на изображение")
            data = resp.read(MAX_ICON_BYTES + 1)
            if len(data) > MAX_ICON_BYTES:
                raise HTTPException(413, "Иконка слишком большая. Максимум 5 МБ")
            ext = _safe_extension(urllib.parse.urlparse(resp.geturl()).path, content_type)
            if not ext:
                raise HTTPException(400, "Не удалось определить формат изображения")
            return data, ext
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Не удалось скачать иконку: {exc}")


@app.post("/api/icons/upload")
async def upload_icon(file: UploadFile = File(...)):
    ext = _safe_extension(file.filename or "", file.content_type or "")
    if not ext:
        raise HTTPException(400, "Поддерживаются PNG, JPG, WEBP, GIF и ICO")
    data = await file.read(MAX_ICON_BYTES + 1)
    return {"icon": _save_icon_bytes(data, ext)}


@app.post("/api/icons/from-url")
def icon_from_url(payload: dict):
    url = str(payload.get("url", "")).strip()
    if not url:
        raise HTTPException(400, "Укажите URL изображения")
    data, ext = _download_image(url)
    return {"icon": _save_icon_bytes(data, ext)}


@app.get("/api/tile-background/{filename}")
def serve_tile_background(filename: str):
    # Serve tile backgrounds through an explicit API route as well as the
    # static mount. This keeps existing stored paths compatible while avoiding
    # browser/cache routing surprises after a Dashboard refresh.
    safe_name = Path(filename).name
    path = TILE_BACKGROUNDS_DIR / safe_name
    if not path.is_file():
        raise HTTPException(404, "Фон плитки не найден")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "public, max-age=31536000, immutable"})


@app.post("/api/tile-background/upload")
async def upload_tile_background(file: UploadFile = File(...)):
    """Save a tile-specific background in the persistent backgrounds directory."""
    ext = _safe_background_extension(file.filename or "", file.content_type or "")
    if not ext:
        raise HTTPException(400, "Поддерживаются PNG, JPG, WEBP и GIF")
    data = await file.read(MAX_BACKGROUND_BYTES + 1)
    return {"url": _save_tile_background_bytes(data, ext)}


@app.post("/api/tile-background/from-url")
def tile_background_from_url(payload: dict):
    """Download a tile-specific background and save it persistently."""
    url = str(payload.get("url", "")).strip()
    if not url:
        raise HTTPException(400, "Укажите URL изображения")
    if url.startswith(("/backgrounds/", "/tile-backgrounds/")):
        return {"url": url}
    data, ext = _download_background(url)
    return {"url": _save_tile_background_bytes(data, ext)}


class FaviconParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.icons: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "link":
            return
        attrs_dict = {k.lower(): (v or "") for k, v in attrs}
        rel = attrs_dict.get("rel", "").lower().split()
        href = attrs_dict.get("href", "").strip()
        if href and ("icon" in rel or "shortcut" in rel):
            self.icons.append(href)


def _favicon_candidates(site_url: str) -> list[str]:
    parsed = urllib.parse.urlparse(site_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "URL приложения должен начинаться с http:// или https://")
    if not _host_is_public(parsed.hostname):
        raise HTTPException(400, "URL ведёт на локальный или недоступный адрес")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [urllib.parse.urljoin(origin + "/", "favicon.ico")]
    try:
        req = urllib.request.Request(site_url, headers={"User-Agent": "My-DashboardKDV/4.2", "Accept": "text/html,*/*;q=0.8"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status < 400 and "text/html" in (resp.headers.get("Content-Type", "") or ""):
                body = resp.read(512 * 1024).decode("utf-8", errors="ignore")
                parser = FaviconParser()
                parser.feed(body)
                for href in parser.icons[:10]:
                    candidates.append(urllib.parse.urljoin(site_url, href))
    except Exception:
        pass
    seen = set()
    return [x for x in candidates if not (x in seen or seen.add(x))]


@app.post("/api/icons/favicon")
def favicon_from_site(payload: dict):
    site_url = str(payload.get("url", "")).strip()
    for candidate in _favicon_candidates(site_url):
        try:
            data, ext = _download_image(candidate)
            return {"icon": _save_icon_bytes(data, ext), "source": candidate}
        except HTTPException:
            continue
    raise HTTPException(400, "Не удалось найти favicon этого сайта")


# ---------------- Background image ----------------
@app.get("/api/background")
def get_background():
    return _background_settings()


@app.post("/api/background/upload")
async def upload_background(file: UploadFile = File(...)):
    ext = _safe_background_extension(file.filename or "", file.content_type or "")
    if not ext:
        raise HTTPException(400, "Поддерживаются PNG, JPG, WEBP и GIF")
    data = await file.read(MAX_BACKGROUND_BYTES + 1)
    return {"url": _save_background_bytes(data, ext)}


def _download_background(url: str) -> tuple[bytes, str]:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "Разрешены только HTTP и HTTPS ссылки")
    if len(url) > 2048:
        raise HTTPException(400, "Ссылка слишком длинная")
    if not _host_is_public(parsed.hostname):
        raise HTTPException(400, "Ссылка ведёт на локальный или недоступный адрес")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "My-DashboardKDV/4.4", "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0].lower()
            if content_type.startswith("text/") or content_type in {"application/json", "application/javascript"}:
                raise HTTPException(400, "Ссылка не ведёт на изображение")
            data = resp.read(MAX_BACKGROUND_BYTES + 1)
            if len(data) > MAX_BACKGROUND_BYTES:
                raise HTTPException(413, "Фоновое изображение слишком большое. Максимум 8 МБ")
            ext = _safe_background_extension(urllib.parse.urlparse(resp.geturl()).path, content_type)
            if not ext:
                raise HTTPException(400, "Не удалось определить формат изображения")
            return data, ext
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Не удалось скачать фоновое изображение: {exc}")


@app.post("/api/background/from-url")
def background_from_url(payload: dict):
    url = str(payload.get("url", "")).strip()
    if not url:
        raise HTTPException(400, "Укажите URL изображения")
    data, ext = _download_background(url)
    return {"url": _save_background_bytes(data, ext)}


@app.put("/api/background")
def update_background(payload: dict):
    opacity = 1.0
    enabled = bool(payload.get("enabled", True))
    with db() as conn:
        conn.execute(
            """INSERT INTO background_settings(id,path,opacity,enabled) VALUES(1,COALESCE((SELECT path FROM background_settings WHERE id=1),?),?,?)
            ON CONFLICT(id) DO UPDATE SET opacity=excluded.opacity,enabled=excluded.enabled""",
            (str(payload.get("url", "")).strip(), opacity, int(enabled)),
        )
    return _background_settings()


@app.delete("/api/background")
def delete_background():
    old = _background_settings()
    with db() as conn:
        conn.execute("UPDATE background_settings SET path='',enabled=0 WHERE id=1")
    if old.get("url", "").startswith("/backgrounds/"):
        old_name = Path(old["url"].removeprefix("/backgrounds/")).name
        old_path = BACKGROUNDS_DIR / old_name
        if old_path.exists() and old_path.is_file():
            try:
                old_path.unlink()
            except OSError:
                pass
    return _background_settings()


# ---------------- Emby integration ----------------
def _normalise_emby_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "URL Emby должен начинаться с http:// или https://")
    if parsed.query or parsed.fragment:
        raise HTTPException(400, "URL Emby не должен содержать query-параметры или fragment")
    path = parsed.path.rstrip("/")
    if path.lower().endswith("/emby"):
        path = path[:-5]
    return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")


def _emby_api_base(base_url: str) -> str:
    base = _normalise_emby_url(base_url)
    return (base + "/emby") if base else ""


def _emby_request(base_url: str, api_key: str, path: str):
    target = _emby_api_base(base_url) + path
    req = urllib.request.Request(
        target,
        headers={
            "Accept": "application/json",
            "X-Emby-Token": api_key,
            "User-Agent": "My-DashboardKDV/4.4",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = resp.read(2 * 1024 * 1024)
            return resp.status, json.loads(payload.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(1000).decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}" + (f": {detail[:200]}" if detail else "")) from exc
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _emby_transcoding_active(session: dict) -> bool:
    info = session.get("TranscodingInfo")
    if isinstance(info, list):
        return any(bool(x) for x in info)
    return bool(info)


def _emby_status_from_session(session: dict) -> dict:
    item = session.get("NowPlayingItem") or {}
    play_state = session.get("PlayState") or {}
    runtime = item.get("RunTimeTicks") or 0
    position = play_state.get("PositionTicks") or 0
    percent = round((position / runtime) * 100, 1) if runtime else 0
    return {
        "user": session.get("UserName") or "—",
        "device": session.get("DeviceName") or session.get("Client") or "—",
        "client": session.get("Client") or "—",
        "title": item.get("Name") or "",
        "series": item.get("SeriesName") or "",
        "paused": bool(play_state.get("IsPaused")),
        "percent": max(0, min(100, percent)),
        "play_method": play_state.get("PlayMethod") or "",
        "transcoding": _emby_transcoding_active(session),
    }


@app.get("/api/emby/config")
def get_emby_config():
    with db() as conn:
        row = conn.execute("SELECT name,url,enabled FROM emby_settings WHERE id=1").fetchone()
    if not row:
        return {"configured": False, "name": "Emby", "url": "", "enabled": True}
    return {
        "configured": bool(row["url"]),
        "name": row["name"],
        "url": row["url"],
        "enabled": bool(row["enabled"]),
    }


@app.put("/api/emby/config")
def save_emby_config(config: EmbyConfig):
    url = _normalise_emby_url(config.url)
    name = config.name.strip() or "Emby"
    with db() as conn:
        current = conn.execute("SELECT api_key FROM emby_settings WHERE id=1").fetchone()
        api_key = config.api_key.strip() if config.api_key.strip() else (current["api_key"] if current else "")
        conn.execute(
            """INSERT INTO emby_settings(id,name,url,api_key,enabled) VALUES(1,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url,api_key=excluded.api_key,enabled=excluded.enabled""",
            (name, url, api_key, int(config.enabled)),
        )
    return {"ok": True, "configured": bool(url), "name": name, "url": url, "enabled": bool(config.enabled)}


@app.get("/api/emby/status")
def emby_status():
    with db() as conn:
        row = conn.execute("SELECT name,url,api_key,enabled FROM emby_settings WHERE id=1").fetchone()
    if not row or not row["enabled"] or not row["url"]:
        return {"configured": False, "enabled": bool(row["enabled"]) if row else True}
    api_key = row["api_key"]
    if not api_key:
        return {"configured": True, "enabled": True, "online": False, "name": row["name"], "error": "Не указан API ключ Emby"}
    started = perf_counter()
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        _, info = _emby_request(row["url"], api_key, "/System/Info")
        _, sessions = _emby_request(row["url"], api_key, "/Sessions")
        sessions = sessions if isinstance(sessions, list) else []
        playing = [s for s in sessions if s.get("NowPlayingItem")]
        transcode_count = sum(1 for s in playing if _emby_transcoding_active(s))
        users = len({s.get("UserName") for s in sessions if s.get("UserName")})
        latency_ms = round((perf_counter() - started) * 1000)
        return {
            "configured": True,
            "enabled": True,
            "online": True,
            "name": row["name"],
            "server_name": info.get("ServerName") or row["name"],
            "version": info.get("Version") or "—",
            "server_id": info.get("Id") or "",
            "sessions": len(sessions),
            "playing": len(playing),
            "transcoding": transcode_count,
            "users": users,
            "latency_ms": latency_ms,
            "checked_at": checked_at,
            "players": [_emby_status_from_session(s) for s in playing[:12]],
        }
    except Exception as exc:
        latency_ms = round((perf_counter() - started) * 1000)
        return {
            "configured": True,
            "enabled": True,
            "online": False,
            "name": row["name"],
            "latency_ms": latency_ms,
            "checked_at": checked_at,
            "error": str(exc)[:300],
        }


@app.post("/api/emby/test")
def test_emby_connection(payload: dict):
    url = _normalise_emby_url(str(payload.get("url", "")).strip())
    api_key = str(payload.get("api_key", "")).strip()
    if not url:
        raise HTTPException(400, "Укажите URL Emby")
    if not api_key:
        with db() as conn:
            row = conn.execute("SELECT api_key FROM emby_settings WHERE id=1").fetchone()
        api_key = row["api_key"] if row else ""
    if not api_key:
        raise HTTPException(400, "Укажите API ключ Emby")
    started = perf_counter()
    try:
        _, info = _emby_request(url, api_key, "/System/Info")
        return {
            "online": True,
            "server_name": info.get("ServerName") or "Emby",
            "version": info.get("Version") or "—",
            "latency_ms": round((perf_counter() - started) * 1000),
        }
    except Exception as exc:
        return {
            "online": False,
            "error": str(exc)[:300],
            "latency_ms": round((perf_counter() - started) * 1000),
        }


@app.get("/api/preferences")
def get_preferences():
    with db() as conn:
        row = conn.execute("SELECT theme FROM dashboard_preferences WHERE id=1").fetchone()
    return {"theme": row["theme"] if row else "dark"}


@app.put("/api/preferences")
def update_preferences(payload: dict):
    theme = "light" if str(payload.get("theme", "dark")).lower() == "light" else "dark"
    with db() as conn:
        conn.execute(
            "INSERT INTO dashboard_preferences(id,theme) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET theme=excluded.theme",
            (theme,),
        )
    return {"theme": theme}


def _read_local_asset(path_value: str) -> tuple[str, Path] | None:
    value = str(path_value or "").strip()
    if value.startswith("/icons/"):
        name = Path(value.removeprefix("/icons/")).name
        path = ICONS_DIR / name
        kind = "icon"
    elif value.startswith("/backgrounds/"):
        name = Path(value.removeprefix("/backgrounds/")).name
        path = BACKGROUNDS_DIR / name
        kind = "background"
    elif value.startswith("/api/tile-background/"):
        name = Path(value.removeprefix("/api/tile-background/")).name
        path = TILE_BACKGROUNDS_DIR / name
        kind = "tile-background"
    elif value.startswith("/tile-backgrounds/"):
        name = Path(value.removeprefix("/tile-backgrounds/")).name
        path = TILE_BACKGROUNDS_DIR / name
        kind = "tile-background"
    else:
        return None
    if not name or not path.exists() or not path.is_file():
        return None
    return kind, path


def _asset_entry(path_value: str) -> dict | None:
    item = _read_local_asset(path_value)
    if not item:
        return None
    kind, path = item
    size_limit = MAX_ICON_BYTES if kind == "icon" else MAX_BACKGROUND_BYTES
    data = path.read_bytes()
    if len(data) > size_limit:
        return None
    mime = mimetypes.guess_type(path.name)[0] or ("image/x-icon" if path.suffix.lower() == ".ico" else "application/octet-stream")
    return {
        "path": path_value,
        "kind": kind,
        "name": path.name,
        "mime": mime,
        "data": "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii")),
    }


def _restore_assets(assets: list[dict]) -> dict[str, str]:
    path_map: dict[str, str] = {}
    total = 0
    for asset in assets or []:
        if not isinstance(asset, dict):
            continue
        old_path = str(asset.get("path") or "").strip()
        kind = str(asset.get("kind") or "")
        data_url = str(asset.get("data") or "")
        if kind not in {"icon", "background", "tile-background"} or not old_path or not data_url.startswith("data:") or ";base64," not in data_url:
            continue
        try:
            header, encoded = data_url.split(",", 1)
            mime = header[5:].split(";", 1)[0].lower()
            raw = base64.b64decode(encoded, validate=True)
        except Exception:
            continue
        limit = MAX_ICON_BYTES if kind == "icon" else MAX_BACKGROUND_BYTES
        total += len(raw)
        if len(raw) > limit or total > 100 * 1024 * 1024:
            raise ValueError("Суммарный объём изображений в импорте не должен превышать 100 МБ")
        name = Path(str(asset.get("name") or "")).name
        if not name:
            continue
        ext = Path(name).suffix.lower()
        allowed = ALLOWED_ICON_EXTENSIONS if kind == "icon" else ALLOWED_BACKGROUND_EXTENSIONS
        if ext not in allowed:
            ext = _safe_background_extension(name, mime) if kind != "icon" else _safe_extension(name, mime)
        if not ext or ext not in allowed:
            continue
        safe_name = f"{uuid.uuid4().hex}{ext}"
        if kind == "icon":
            target = ICONS_DIR / safe_name
            new_path = f"/icons/{safe_name}"
        elif kind == "background":
            target = BACKGROUNDS_DIR / safe_name
            new_path = f"/backgrounds/{safe_name}"
        else:
            target = TILE_BACKGROUNDS_DIR / safe_name
            new_path = f"/api/tile-background/{safe_name}"
        target.write_bytes(raw)
        path_map[old_path] = new_path
    return path_map


@app.get("/api/settings/export")
def export_settings(theme: str = "dark"):
    from datetime import datetime, timezone
    import base64

    with db() as conn:
        categories = [dict(r) for r in conn.execute("SELECT id,name,icon,sort_order FROM categories ORDER BY sort_order,id").fetchall()]
        apps = [dict(r) for r in conn.execute("""SELECT id,name,url,description,category_id,icon,favorite,open_mode,size,status_enabled,sort_order,
        tile_bg_mode,tile_bg_value,tile_bg_scale,tile_opacity,tile_blur,tile_icon_size,tile_title_size,tile_title_color,tile_description_color,tile_url_color,tile_show_description,tile_show_url
        FROM apps ORDER BY sort_order,id""").fetchall()]
    for item in apps:
        item["favorite"] = bool(item["favorite"])

    background = _background_settings()
    background_export = {"enabled": background.get("enabled", False), "url": "", "opacity": 1.0}
    assets: dict[str, dict] = {}

    def add_asset(value: str):
        entry = _asset_entry(value)
        if entry:
            assets.setdefault(entry["path"], entry)

    for item in categories:
        add_asset(str(item.get("icon") or ""))
    for item in apps:
        add_asset(str(item.get("icon") or ""))
        add_asset(str(item.get("tile_bg_value") or ""))

    bg_path = str(background.get("url") or "")
    add_asset(bg_path)
    bg_entry = assets.get(bg_path)
    if background.get("enabled") and bg_entry:
        background_export["asset_path"] = bg_entry["path"]

    with db() as conn:
        pref_row = conn.execute("SELECT theme FROM dashboard_preferences WHERE id=1").fetchone()
    stored_theme = pref_row["theme"] if pref_row else ("light" if theme == "light" else "dark")

    return {
        "version": 8,
        "app_name": "My DashboardKDV",
        "theme": "light" if stored_theme == "light" else "dark",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "categories": categories,
        "apps": apps,
        "emby": get_emby_config(),
        "background": background_export,
        "appearance": _appearance_settings(),
        "assets": list(assets.values()),
        "preferences": {"theme": "light" if stored_theme == "light" else "dark"},
    }


@app.post("/api/settings/import")
def import_settings(settings: DashboardSettings):
    old_to_new = {}
    path_map: dict[str, str] = {}
    try:
        raw_settings = settings.model_dump() if hasattr(settings, "model_dump") else dict(settings)
        path_map = _restore_assets(raw_settings.get("assets", []))
        with db() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM apps")
            conn.execute("DELETE FROM categories")
            for category in settings.categories:
                cur = conn.execute(
                    "INSERT INTO categories(name,icon,sort_order) VALUES (?,?,?)",
                    (category.name.strip(), path_map.get(category.icon.strip(), category.icon.strip()) or "📁", int(getattr(category, "sort_order", 0))),
                )
                old_to_new[category.id] = cur.lastrowid
            has_explicit_order = any(getattr(app_item, "sort_order", 0) != 0 for app_item in settings.apps)
            for index, app_item in enumerate(settings.apps):
                new_category_id = old_to_new.get(app_item.category_id)
                if new_category_id is None:
                    raise ValueError(f"Категория для приложения «{app_item.name}» не найдена")
                sort_order = int(app_item.sort_order) if has_explicit_order else index
                conn.execute(
                    """INSERT INTO apps(name,url,description,category_id,icon,favorite,open_mode,size,status_enabled,sort_order,
                    tile_bg_mode,tile_bg_value,tile_bg_scale,tile_opacity,tile_blur,tile_icon_size,tile_title_size,tile_title_color,tile_description_color,tile_url_color,tile_show_description,tile_show_url)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        app_item.name.strip(),
                        app_item.url.strip(),
                        app_item.description.strip(),
                        new_category_id,
                        path_map.get(app_item.icon.strip(), app_item.icon.strip()) or "🚀",
                        int(app_item.favorite),
                        app_item.open_mode,
                        app_item.size if app_item.size in APP_TILE_SIZES else "medium",
                        int(app_item.status_enabled),
                        sort_order,
                        app_item.tile_bg_mode,
                        path_map.get(app_item.tile_bg_value.strip(), app_item.tile_bg_value.strip()),
                        app_item.tile_bg_scale,
                        app_item.tile_opacity,
                        app_item.tile_blur,
                        app_item.tile_icon_size,
                        app_item.tile_title_size,
                        app_item.tile_title_color,
                        app_item.tile_description_color,
                        app_item.tile_url_color,
                        int(app_item.tile_show_description),
                        int(app_item.tile_show_url),
                    ),
                )
            emby = settings.model_dump().get("emby") if hasattr(settings, "model_dump") else None
            if isinstance(emby, dict):
                emby_url = _normalise_emby_url(str(emby.get("url", "")))
                current_emby = conn.execute("SELECT api_key FROM emby_settings WHERE id=1").fetchone()
                keep_key = current_emby["api_key"] if current_emby else ""
                conn.execute(
                    """INSERT INTO emby_settings(id,name,url,api_key,enabled) VALUES(1,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url,api_key=excluded.api_key,enabled=excluded.enabled""",
                    (str(emby.get("name") or "Emby")[:100], emby_url, keep_key, int(bool(emby.get("enabled", True)))),
                )

            background = settings.model_dump().get("background") if hasattr(settings, "model_dump") else None
            if isinstance(background, dict):
                opacity = 1.0
                bg_url = path_map.get(str(background.get("asset_path") or ""), "")
                bg_data = str(background.get("data", ""))
                if not bg_url and bg_data.startswith("data:") and ";base64," in bg_data:
                    header, encoded = bg_data.split(",", 1)
                    mime = header[5:].split(";", 1)[0].lower()
                    ext = _safe_background_extension("", mime)
                    if not ext:
                        raise ValueError("Неподдерживаемый формат фонового изображения")
                    raw = base64.b64decode(encoded, validate=True)
                    if len(raw) > MAX_BACKGROUND_BYTES:
                        raise ValueError("Фоновое изображение слишком большое. Максимум 8 МБ")
                    name = f"{uuid.uuid4().hex}{ext}"
                    (BACKGROUNDS_DIR / name).write_bytes(raw)
                    bg_url = f"/backgrounds/{name}"
                conn.execute(
                    "UPDATE background_settings SET path=?,opacity=?,enabled=? WHERE id=1",
                    (bg_url, opacity, int(bool(background.get("enabled", bool(bg_url))))),
                )

            appearance = settings.model_dump().get("appearance") if hasattr(settings, "model_dump") else None
            if isinstance(appearance, dict):
                card_opacity = max(0.45, min(1.0, float(appearance.get("card_opacity", 0.90))))
                card_blur = max(0.0, min(20.0, float(appearance.get("card_blur", 6.0))))
                background_blur = max(0.0, min(12.0, float(appearance.get("background_blur", 2.0))))
                background_dim = max(0.0, min(0.85, float(appearance.get("background_dim", 0.55))))
                status_checks_enabled = bool(appearance.get("status_checks_enabled", True))
                conn.execute(
                    """INSERT INTO appearance_settings(id,card_opacity,card_blur,background_blur,background_dim,status_checks_enabled) VALUES(1,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET card_opacity=excluded.card_opacity,card_blur=excluded.card_blur,background_blur=excluded.background_blur,background_dim=excluded.background_dim,status_checks_enabled=excluded.status_checks_enabled""",
                    (card_opacity, card_blur, background_blur, background_dim, int(status_checks_enabled)),
                )

            preferences = raw_settings.get("preferences") if isinstance(raw_settings, dict) else None
            if isinstance(preferences, dict):
                theme = "light" if str(preferences.get("theme", "dark")).lower() == "light" else "dark"
                conn.execute(
                    "INSERT INTO dashboard_preferences(id,theme) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET theme=excluded.theme",
                    (theme,),
                )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(400, f"Не удалось импортировать настройки: {exc}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "categories": len(settings.categories), "apps": len(settings.apps)}
