"""CodeAlpha Task 3 — Cloud-based bus pass system."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "transit.db"
SECRET = os.getenv("APP_SECRET", "codealpha-transitcloud-dev-secret")
INSTANCE_ID = os.getenv("HOSTNAME", "")[:12] or uuid.uuid4().hex[:8]

CATALOGUE = [
    {
        "id": 1,
        "origin": "Mumbai",
        "destination": "Pune",
        "distance_km": 148,
        "operator": "West Corridor Express",
        "departures": 42,
        "load": 71,
        "daily": 450,
        "weekly": 2200,
        "monthly": 7200,
        "student": 5400,
    },
    {
        "id": 2,
        "origin": "Delhi",
        "destination": "Jaipur",
        "distance_km": 281,
        "operator": "Pink City Line",
        "departures": 28,
        "load": 64,
        "daily": 680,
        "weekly": 3300,
        "monthly": 9800,
        "student": 7350,
    },
    {
        "id": 3,
        "origin": "Bengaluru",
        "destination": "Mysuru",
        "distance_km": 143,
        "operator": "Garden City Shuttle",
        "departures": 36,
        "load": 83,
        "daily": 320,
        "weekly": 1600,
        "monthly": 5400,
        "student": 3900,
    },
    {
        "id": 4,
        "origin": "Chennai",
        "destination": "Puducherry",
        "distance_km": 135,
        "operator": "Coastal Link",
        "departures": 22,
        "load": 48,
        "daily": 290,
        "weekly": 1450,
        "monthly": 4900,
        "student": 3600,
    },
    {
        "id": 5,
        "origin": "Hyderabad",
        "destination": "Vijayawada",
        "distance_km": 275,
        "operator": "Deccan Rapid",
        "departures": 18,
        "load": 57,
        "daily": 610,
        "weekly": 2950,
        "monthly": 8900,
        "student": 6700,
    },
]
ROUTE_BY_ID = {r["id"]: r for r in CATALOGUE}
DURATIONS = {"daily": 1, "weekly": 7, "monthly": 30, "student": 30}

app = FastAPI(title="TransitCloud", version="1.0.0")
app.add_middleware(SessionMiddleware, secret_key=SECRET, same_site="lax")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()
    return hmac.compare_digest(check, digest)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'passenger'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS passes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pass_code TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                route_id INTEGER NOT NULL,
                pass_type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT NOT NULL,
                valid_from TEXT NOT NULL,
                valid_until TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                ("Asha Passenger", "passenger@nimbus.cloud", hash_password("passenger123"), "passenger"),
            )
            conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
                ("Rohan Ops", "admin@nimbus.cloud", hash_password("admin123"), "admin"),
            )


def current_user(request: Request) -> dict[str, Any] | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return dict(row) if row else None


def render(request: Request, name: str, **context: Any) -> HTMLResponse:
    user = current_user(request)
    return templates.TemplateResponse(
        name,
        {
            "request": request,
            "user": user,
            "flash": request.session.pop("flash", None),
            "flash_ok": request.session.pop("flash_ok", False),
            "instance_id": INSTANCE_ID,
            **context,
        },
    )


def flash(request: Request, message: str, ok: bool = False) -> None:
    request.session["flash"] = message
    request.session["flash_ok"] = ok


def issue_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"TC-{body}"


def catalogue_amount(route: dict[str, Any], pass_type: str) -> int:
    if pass_type not in DURATIONS:
        raise KeyError("unknown pass type")
    return int(route[pass_type])


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "transitcloud",
        "instance": INSTANCE_ID,
        "time": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/routes")
def api_routes() -> list[dict[str, Any]]:
    return CATALOGUE


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return render(request, "index.html", routes=CATALOGUE)


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request) -> HTMLResponse:
    return render(request, "auth.html", mode="Register")


@app.post("/register")
def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    email = email.strip().lower()
    if len(password) < 8:
        flash(request, "Password must be at least 8 characters.")
        return RedirectResponse("/register", status_code=303)
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, 'passenger')",
                (name.strip(), email, hash_password(password)),
            )
            request.session["uid"] = cur.lastrowid
    except sqlite3.IntegrityError:
        flash(request, "That email is already registered.")
        return RedirectResponse("/register", status_code=303)
    flash(request, "Account created. Your passes will live in this cloud wallet.", True)
    return RedirectResponse("/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request) -> HTMLResponse:
    return render(request, "auth.html", mode="Login")


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        flash(request, "Email or password is incorrect.")
        return RedirectResponse("/login", status_code=303)
    request.session["uid"] = row["id"]
    return RedirectResponse("/", status_code=303)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.post("/book")
def book(request: Request, route_id: int = Form(...), pass_type: str = Form(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    route = ROUTE_BY_ID.get(route_id)
    if not route:
        flash(request, "Unknown corridor.")
        return RedirectResponse("/", status_code=303)
    try:
        amount = catalogue_amount(route, pass_type)
    except KeyError:
        flash(request, "Unknown pass type. Fare was not accepted from the client.")
        return RedirectResponse("/", status_code=303)

    today = date.today()
    until = today + timedelta(days=DURATIONS[pass_type])
    with db() as conn:
        existing = conn.execute(
            """
            SELECT id FROM passes
            WHERE user_id = ? AND route_id = ? AND pass_type = ? AND status = 'active'
              AND valid_until >= ?
            """,
            (user["id"], route_id, pass_type, today.isoformat()),
        ).fetchone()
        if existing:
            flash(request, "An active pass of this type already exists for that corridor. Duplicate booking blocked.")
            return RedirectResponse("/wallet", status_code=303)
        code = issue_code()
        conn.execute(
            """
            INSERT INTO passes
            (pass_code, user_id, route_id, pass_type, amount, status, valid_from, valid_until, created_at)
            VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                code,
                user["id"],
                route_id,
                pass_type,
                amount,
                today.isoformat(),
                until.isoformat(),
                datetime.utcnow().isoformat(),
            ),
        )
    flash(request, f"Pass {code} issued at catalogue fare ₹{amount}. It cannot be lost — reopen it from any device.", True)
    return RedirectResponse(f"/pass/{code}", status_code=303)


def pass_view(row: sqlite3.Row, user: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    route = ROUTE_BY_ID[row["route_id"]]
    return {
        "pass_code": row["pass_code"],
        "origin": route["origin"],
        "destination": route["destination"],
        "pass_type": row["pass_type"],
        "amount": row["amount"],
        "status": row["status"],
        "valid_from": row["valid_from"],
        "valid_until": row["valid_until"],
        "holder_name": user["name"] if isinstance(user, dict) else user["name"],
        "email": user["email"] if isinstance(user, dict) else user["email"],
    }


@app.get("/wallet", response_class=HTMLResponse)
def wallet(request: Request) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM passes WHERE user_id = ? ORDER BY id DESC", (user["id"],)
        ).fetchall()
    return render(request, "wallet.html", passes=[pass_view(r, user) for r in rows])


@app.get("/pass/{code}", response_class=HTMLResponse)
def show_pass(request: Request, code: str) -> HTMLResponse:
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    with db() as conn:
        row = conn.execute("SELECT * FROM passes WHERE pass_code = ?", (code,)).fetchone()
    if not row:
        flash(request, "Pass not found.")
        return RedirectResponse("/wallet", status_code=303)
    if row["user_id"] != user["id"] and user["role"] != "admin":
        flash(request, "That pass is bound to another account (anti-theft).")
        return RedirectResponse("/wallet", status_code=303)
    holder = user
    if row["user_id"] != user["id"]:
        with db() as conn:
            holder = dict(conn.execute("SELECT * FROM users WHERE id = ?", (row["user_id"],)).fetchone())
    return render(request, "pass.html", ticket=pass_view(row, holder))


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request) -> HTMLResponse:
    user = current_user(request)
    if not user or user["role"] != "admin":
        flash(request, "Operations console is restricted.")
        return RedirectResponse("/", status_code=303)
    with db() as conn:
        rows = conn.execute("SELECT * FROM passes ORDER BY id DESC").fetchall()
        users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        revenue = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM passes").fetchone()[0]
        holders = {
            r["id"]: r
            for r in conn.execute("SELECT * FROM users").fetchall()
        }
    views = [pass_view(r, holders[r["user_id"]]) for r in rows]
    return render(
        request,
        "admin.html",
        passes=views,
        stats={"passes": len(rows), "users": users, "revenue": revenue},
    )
