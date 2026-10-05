from pathlib import Path
import hashlib
import json
import html
import ipaddress
import mimetypes
import re
import socket
import sqlite3
import urllib.parse
import urllib.request
import urllib.error
import uuid
from html.parser import HTMLParser
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR.parent / "data"
DB_PATH = DATA_DIR / "dashboard.db"
ICONS_DIR = DATA_DIR / "icons"
BACKGROUNDS_DIR = DATA_DIR / "backgrounds"
STATIC_DIR = BASE_DIR / "static"
DEFAULT_BACKGROUND_SOURCE = STATIC_DIR / "assets" / "default-background.png"
DEFAULT_BACKGROUND_NAME = "my-dashboardkdv-default.png"
DATA_DIR.mkdir(parents=True, exist_ok=True)
ICONS_DIR.mkdir(parents=True, exist_ok=True)
BACKGROUNDS_DIR.mkdir(parents=True, exist_ok=True)

APP_TILE_SIZES = {'small', 'medium', 'large'}
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

app = FastAPI(title="My DashboardKDV", version="1.3.1")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/icons", StaticFiles(directory=ICONS_DIR), name="icons")
app.mount("/backgrounds", StaticFiles(directory=BACKGROUNDS_DIR), name="backgrounds")


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
    size: Literal['small', 'medium', 'large'] = 'medium'


class ExportCategory(BaseModel):
    id: int
    name: str = Field(min_length=1, max_length=100)
    icon: str = Field(default="📁", max_length=500)


class ExportApp(BaseModel):
    id: int
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=300)
    category_id: int
    icon: str = Field(default="🚀", max_length=500)
    favorite: bool = False
    size: Literal['small', 'medium', 'large'] = 'medium'
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
            icon TEXT NOT NULL DEFAULT '📁')"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS apps (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', category_id INTEGER NOT NULL,
            icon TEXT NOT NULL DEFAULT '🚀', favorite INTEGER NOT NULL DEFAULT 0,
            size TEXT NOT NULL DEFAULT 'medium',
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON UPDATE CASCADE ON DELETE RESTRICT)"""
        )
        app_columns = {row['name'] for row in conn.execute("PRAGMA table_info(apps)").fetchall()}
        if 'size' not in app_columns:
            conn.execute("ALTER TABLE apps ADD COLUMN size TEXT NOT NULL DEFAULT 'medium'")
        if 'sort_order' not in app_columns:
            conn.execute("ALTER TABLE apps ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE apps SET size='medium' WHERE size NOT IN ('small','medium','large') OR size IS NULL")
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
            background_dim REAL NOT NULL DEFAULT 0.55
            )"""
        )
        if conn.execute("SELECT 1 FROM appearance_settings WHERE id=1").fetchone() is None:
            conn.execute(
                "INSERT INTO appearance_settings(id,card_opacity,card_blur,background_blur,background_dim) VALUES(1,0.90,6.0,2.0,0.55)"
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
                "INSERT INTO categories(name, icon) VALUES (?, ?)",
                [("Мои приложения", "🚀"), ("Инструменты", "🛠️"), ("Мониторинг", "📊"), ("Docker", "🐳")],
            )
        if conn.execute("SELECT COUNT(*) FROM apps").fetchone()[0] == 0:
            cat = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM categories")}
            conn.executemany(
                """INSERT INTO apps
                (name,url,description,category_id,icon,favorite,size,sort_order) VALUES (?,?,?,?,?,?,?,?)""",
                [
                    ("Video Converter", "http://localhost:8000", "Перекодировка видео", cat["Мои приложения"], "🎬", 1, "medium", 0),
                    ("GitHub", "https://github.com/", "Репозитории и код", cat["Инструменты"], "💻", 1, "medium", 1),
                    ("Docker", "https://www.docker.com/", "Контейнеры и образы", cat["Docker"], "🐳", 1, "medium", 2),
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
            """SELECT c.id,c.name,c.icon,COUNT(a.id) AS app_count FROM categories c
            LEFT JOIN apps a ON a.category_id=c.id GROUP BY c.id ORDER BY c.id"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/categories")
def create_category(item: Category):
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO categories(name,icon) VALUES (?,?)", (item.name.strip(), item.icon.strip() or "📁")
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


@app.get("/api/apps")
def list_apps():
    with db() as conn:
        rows = conn.execute(
            """SELECT a.id,a.name,a.url,a.description,a.category_id,a.icon,a.favorite,a.size,a.sort_order,
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
            "INSERT INTO apps(name,url,description,category_id,icon,favorite,size,sort_order) VALUES (?,?,?,?,?,?,?,?)",
            (item.name.strip(), item.url.strip(), item.description.strip(), item.category_id, item.icon.strip() or "🚀", int(item.favorite), item.size, int(next_order)),
        )
        return {"id": cur.lastrowid, **item.model_dump()}


@app.put("/api/apps/{app_id}")
def update_app(app_id: int, item: AppItem):
    with db() as conn:
        if not conn.execute("SELECT id FROM categories WHERE id=?", (item.category_id,)).fetchone():
            raise HTTPException(400, "Категория не найдена")
        cur = conn.execute(
            "UPDATE apps SET name=?,url=?,description=?,category_id=?,icon=?,favorite=?,size=? WHERE id=?",
            (item.name.strip(), item.url.strip(), item.description.strip(), item.category_id, item.icon.strip() or "🚀", int(item.favorite), item.size, app_id),
        )
        if not cur.rowcount:
            raise HTTPException(404, "Приложение не найдено")
    return {"id": app_id, **item.model_dump()}


@app.delete("/api/apps/{app_id}")
def delete_app(app_id: int):
    with db() as conn:
        if not conn.execute("DELETE FROM apps WHERE id=?", (app_id,)).rowcount:
            raise HTTPException(404, "Приложение не найдено")
    return {"ok": True}


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


def _appearance_settings() -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT card_opacity,card_blur,background_blur,background_dim FROM appearance_settings WHERE id=1"
        ).fetchone()
    if not row:
        return {"card_opacity": 0.90, "card_blur": 6.0, "background_blur": 2.0, "background_dim": 0.55}
    return {
        "card_opacity": max(0.45, min(1.0, float(row["card_opacity"] or 0.90))),
        "card_blur": max(0.0, min(20.0, float(row["card_blur"] or 6.0))),
        "background_blur": max(0.0, min(12.0, float(row["background_blur"] or 2.0))),
        "background_dim": max(0.0, min(0.85, float(row["background_dim"] or 0.55))),
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
            """INSERT INTO appearance_settings(id,card_opacity,card_blur,background_blur,background_dim) VALUES(1,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET card_opacity=excluded.card_opacity,card_blur=excluded.card_blur,background_blur=excluded.background_blur,background_dim=excluded.background_dim""",
            (card_opacity, card_blur, background_blur, background_dim),
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
        return {"configured": True, "enabled": True, "online": False, "error": "Не указан API ключ Emby"}
    try:
        _, info = _emby_request(row["url"], api_key, "/System/Info")
        _, sessions = _emby_request(row["url"], api_key, "/Sessions")
        sessions = sessions if isinstance(sessions, list) else []
        playing = [s for s in sessions if s.get("NowPlayingItem")]
        transcode_count = sum(1 for s in playing if _emby_transcoding_active(s))
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
            "players": [_emby_status_from_session(s) for s in playing[:12]],
        }
    except Exception as exc:
        return {
            "configured": True,
            "enabled": True,
            "online": False,
            "name": row["name"],
            "error": str(exc)[:300],
        }


@app.get("/api/settings/export")
def export_settings(theme: str = "dark"):
    from datetime import datetime, timezone
    import base64

    with db() as conn:
        categories = [dict(r) for r in conn.execute("SELECT id,name,icon FROM categories ORDER BY id").fetchall()]
        apps = [dict(r) for r in conn.execute("SELECT id,name,url,description,category_id,icon,favorite,size,sort_order FROM apps ORDER BY sort_order,id").fetchall()]
    for item in apps:
        item["favorite"] = bool(item["favorite"])

    background = _background_settings()
    background_export = {"enabled": background.get("enabled", False), "url": "", "opacity": 1.0}
    bg_file = _background_file_for_export()
    if background.get("enabled") and bg_file:
        mime = mimetypes.guess_type(bg_file.name)[0] or "image/jpeg"
        background_export["mime"] = mime
        background_export["data"] = "data:%s;base64,%s" % (mime, base64.b64encode(bg_file.read_bytes()).decode("ascii"))

    return {
        "version": 4,
        "app_name": "My DashboardKDV",
        "theme": "light" if theme == "light" else "dark",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "categories": categories,
        "apps": apps,
        "emby": get_emby_config(),
        "background": background_export,
        "appearance": _appearance_settings(),
    }


@app.post("/api/settings/import")
def import_settings(settings: DashboardSettings):
    old_to_new = {}
    try:
        with db() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("DELETE FROM apps")
            conn.execute("DELETE FROM categories")
            for category in settings.categories:
                cur = conn.execute(
                    "INSERT INTO categories(name,icon) VALUES (?,?)",
                    (category.name.strip(), category.icon.strip() or "📁"),
                )
                old_to_new[category.id] = cur.lastrowid
            has_explicit_order = any(getattr(app_item, "sort_order", 0) != 0 for app_item in settings.apps)
            for index, app_item in enumerate(settings.apps):
                new_category_id = old_to_new.get(app_item.category_id)
                if new_category_id is None:
                    raise ValueError(f"Категория для приложения «{app_item.name}» не найдена")
                sort_order = int(app_item.sort_order) if has_explicit_order else index
                conn.execute(
                    "INSERT INTO apps(name,url,description,category_id,icon,favorite,size,sort_order) VALUES (?,?,?,?,?,?,?,?)",
                    (
                        app_item.name.strip(),
                        app_item.url.strip(),
                        app_item.description.strip(),
                        new_category_id,
                        app_item.icon.strip() or "🚀",
                        int(app_item.favorite),
                        app_item.size if app_item.size in APP_TILE_SIZES else "medium",
                        sort_order,
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
                bg_url = ""
                bg_data = str(background.get("data", ""))
                if bg_data.startswith("data:") and ";base64," in bg_data:
                    import base64
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
                conn.execute(
                    """INSERT INTO appearance_settings(id,card_opacity,card_blur,background_blur,background_dim) VALUES(1,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET card_opacity=excluded.card_opacity,card_blur=excluded.card_blur,background_blur=excluded.background_blur,background_dim=excluded.background_dim""",
                    (card_opacity, card_blur, background_blur, background_dim),
                )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(400, f"Не удалось импортировать настройки: {exc}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "categories": len(settings.categories), "apps": len(settings.apps)}
