"""
Landscaping Contractor Management Application
===========================================

This module implements a small web application for landscaping contractors using
FastAPI.  The app allows you to manage clients, jobs, tasks and invoices.
It uses SQLite as its storage backend via the built‑in `sqlite3` module.

You can run this application locally with:

```bash
python app.py
```

Or from the project folder: `run.bat` (Windows) / `./run.ps1` (PowerShell).
Uses port 5050 by default (set PORT=8080 etc. to override). Visit http://localhost:5050/

The user interface is intentionally simple and responsive.  Data persists in
`landscaping.db` in the project directory.  If the database does not exist it
is created automatically on startup.
"""

import calendar
import os
import sqlite3
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:
    # WeasyPrint is optional; used only for invoice PDF generation.
    from weasyprint import HTML as _WeasyHTML
    _WEASYPRINT_AVAILABLE = True
except Exception:
    _WEASYPRINT_AVAILABLE = False

if os.getenv("VERCEL"):
    # Vercel functions can only write to /tmp at runtime.
    DATABASE_PATH = "/tmp/landscaping.db"
else:
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), "landscaping.db")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()


def init_db() -> None:
    """Initialise the SQLite database if it doesn't exist.

    Creates tables for clients, jobs and tasks.  Uses simple schema with
    autoincrementing primary keys.
    """
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                phone TEXT,
                email TEXT
            );
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS crews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            );
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                scheduled_date TEXT NOT NULL,
                crew TEXT,
                crew_id INTEGER,
                estimated_hours REAL,
                estimated_cost REAL,
                actual_hours REAL,
                actual_cost REAL,
                status TEXT NOT NULL DEFAULT 'Scheduled',
                invoice_sent_at TEXT,
                invoice_status TEXT,
                paid_at TEXT,
                on_my_way_sent_at TEXT,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(crew_id) REFERENCES crews(id)
            );
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id INTEGER NOT NULL,
                description TEXT NOT NULL,
                estimated_hours REAL NOT NULL,
                estimated_cost REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Draft',
                created_at TEXT,
                valid_until TEXT,
                job_id INTEGER,
                FOREIGN KEY(client_id) REFERENCES clients(id),
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                method TEXT NOT NULL,
                paid_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS job_members (
                job_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                PRIMARY KEY (job_id, member_id),
                FOREIGN KEY (job_id) REFERENCES jobs(id),
                FOREIGN KEY (member_id) REFERENCES members(id)
            );
            """
        )
        conn.commit()
    _migrate_jobs_invoice_columns()
    _migrate_jobs_crew_id()


def _migrate_jobs_invoice_columns() -> None:
    """Add invoice-related columns to jobs if they do not exist (for existing DBs)."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        for col, spec in [
            ("invoice_sent_at", "TEXT"),
            ("invoice_status", "TEXT"),
            ("paid_at", "TEXT"),
            ("on_my_way_sent_at", "TEXT"),
        ]:
            try:
                c.execute(f"ALTER TABLE jobs ADD COLUMN {col} {spec}")
                conn.commit()
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    raise


def _migrate_jobs_crew_id() -> None:
    """Add crew_id to jobs if it does not exist (for existing DBs)."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        c = conn.cursor()
        try:
            c.execute("ALTER TABLE jobs ADD COLUMN crew_id INTEGER REFERENCES crews(id)")
            conn.commit()
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise


def get_connection() -> sqlite3.Connection:
    """Return a new connection to the SQLite database.

    We use row factory to access columns by name.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


app = FastAPI(title="Landscaping Contractor App")

# Initialise database on import
init_db()

# Configure Jinja2 templates
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
templates.env.globals["google_maps_api_key"] = GOOGLE_MAPS_API_KEY

# Crews list supports both /crews and /crews-list.
@app.get("/crews", response_class=HTMLResponse)
@app.get("/crews/", response_class=HTMLResponse)
@app.get("/crews-list", response_class=HTMLResponse, include_in_schema=False)
@app.get("/crews-list/", response_class=HTMLResponse, include_in_schema=False)
def list_crews(request: Request) -> HTMLResponse:
    with get_connection() as conn:
        crews = conn.execute("SELECT * FROM crews ORDER BY name").fetchall()
    return templates.TemplateResponse("crews.html", {"request": request, "crews": crews})


# Members list supports both /members and /members-list.
@app.get("/members", response_class=HTMLResponse)
@app.get("/members/", response_class=HTMLResponse)
@app.get("/members-list", response_class=HTMLResponse, include_in_schema=False)
@app.get("/members-list/", response_class=HTMLResponse, include_in_schema=False)
def list_members(request: Request) -> HTMLResponse:
    with get_connection() as conn:
        members = conn.execute("SELECT * FROM members ORDER BY name").fetchall()
    return templates.TemplateResponse("members.html", {"request": request, "members": members})


@app.get("/team/crews", include_in_schema=False)
@app.get("/team/crews/", include_in_schema=False)
def redirect_team_crews() -> RedirectResponse:
    return RedirectResponse(url="/crews", status_code=302)


@app.get("/team/members", include_in_schema=False)
@app.get("/team/members/", include_in_schema=False)
def redirect_team_members() -> RedirectResponse:
    return RedirectResponse(url="/members", status_code=302)


@app.get("/reports", response_class=HTMLResponse)
def reports(request: Request) -> HTMLResponse:
    """Reports: revenue by month, job counts by status, unpaid completed jobs."""
    with get_connection() as conn:
        revenue_by_month = conn.execute(
            """
            SELECT strftime('%Y-%m', COALESCE(paid_at, scheduled_date)) AS month,
                   SUM(actual_cost) AS total
            FROM jobs WHERE status = 'Completed'
            GROUP BY month ORDER BY month DESC LIMIT 24
            """
        ).fetchall()
        status_counts = conn.execute(
            """
            SELECT status, COUNT(*) AS cnt FROM jobs GROUP BY status ORDER BY status
            """
        ).fetchall()
        unpaid_jobs = conn.execute(
            """
            SELECT jobs.id, jobs.description, jobs.actual_cost, jobs.scheduled_date, clients.name AS client_name
            FROM jobs
            JOIN clients ON jobs.client_id = clients.id
            WHERE jobs.status = 'Completed' AND (jobs.invoice_status IS NULL OR jobs.invoice_status != 'Paid')
            ORDER BY jobs.scheduled_date DESC
            """
        ).fetchall()
    return templates.TemplateResponse(
        "reports.html",
        {
            "request": request,
            "revenue_by_month": revenue_by_month,
            "status_counts": status_counts,
            "unpaid_jobs": unpaid_jobs,
        },
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    """Render the home page displaying a summary of counts, revenue, and unpaid invoices."""
    now = datetime.utcnow()
    this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()[:10]
    this_year_start = f"{now.year}-01-01"
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM clients")
        client_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM jobs WHERE status='Scheduled'")
        scheduled_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM jobs WHERE status='Completed'")
        completed_count = c.fetchone()[0]
        c.execute(
            """
            SELECT COALESCE(SUM(actual_cost), 0) FROM jobs
            WHERE status = 'Completed' AND date(scheduled_date) >= date(?)
            """,
            (this_month_start,),
        )
        revenue_this_month = c.fetchone()[0] or 0
        c.execute(
            """
            SELECT COALESCE(SUM(actual_cost), 0) FROM jobs
            WHERE status = 'Completed' AND date(scheduled_date) >= date(?)
            """,
            (this_year_start,),
        )
        revenue_this_year = c.fetchone()[0] or 0
        c.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(actual_cost), 0) FROM jobs
            WHERE status = 'Completed' AND (invoice_status IS NULL OR invoice_status != 'Paid')
            """
        )
        row = c.fetchone()
        unpaid_count = row[0]
        unpaid_total = row[1] or 0
        c.execute("SELECT COUNT(*) FROM quotes WHERE status = 'Sent'")
        quotes_sent = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM quotes WHERE status = 'Accepted'")
        quotes_accepted = c.fetchone()[0]
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "client_count": client_count,
            "scheduled_count": scheduled_count,
            "completed_count": completed_count,
            "revenue_this_month": revenue_this_month,
            "revenue_this_year": revenue_this_year,
            "unpaid_count": unpaid_count,
            "unpaid_total": unpaid_total,
            "quotes_sent": quotes_sent,
            "quotes_accepted": quotes_accepted,
        },
    )


@app.get("/clients", response_class=HTMLResponse)
def list_clients(request: Request) -> HTMLResponse:
    """List all clients.

    A link is provided to add new clients.
    """
    with get_connection() as conn:
        clients = conn.execute("SELECT * FROM clients ORDER BY name").fetchall()
    return templates.TemplateResponse(
        "clients.html", {"request": request, "clients": clients}
    )


@app.get("/clients/new", response_class=HTMLResponse)
def new_client_form(request: Request) -> HTMLResponse:
    """Display a form for creating a new client."""
    return templates.TemplateResponse("client_form.html", {"request": request})


@app.post("/clients/new")
def create_client(
    name: str = Form(...),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
) -> RedirectResponse:
    """Process submission of the new client form and add the client to the database."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO clients (name, address, phone, email) VALUES (?, ?, ?, ?)",
            (name.strip(), address.strip(), phone.strip(), email.strip()),
        )
        conn.commit()
    return RedirectResponse(url="/clients", status_code=303)


def fetch_client(client_id: int) -> sqlite3.Row:
    """Fetch a client by ID, raising a 404 if not found."""
    with get_connection() as conn:
        client = conn.execute(
            "SELECT * FROM clients WHERE id = ?", (client_id,)
        ).fetchone()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@app.get("/clients/{client_id}", response_class=HTMLResponse)
def view_client(client_id: int, request: Request) -> HTMLResponse:
    """Display client details and list of jobs for this client."""
    client = fetch_client(client_id)
    with get_connection() as conn:
        jobs = conn.execute(
            """
            SELECT id, description, scheduled_date, status
            FROM jobs WHERE client_id = ? ORDER BY datetime(scheduled_date) DESC
            """,
            (client_id,),
        ).fetchall()
    return templates.TemplateResponse(
        "client_detail.html",
        {"request": request, "client": client, "jobs": jobs},
    )


@app.get("/clients/{client_id}/edit", response_class=HTMLResponse)
def edit_client_form(client_id: int, request: Request) -> HTMLResponse:
    """Display form to edit an existing client."""
    client = fetch_client(client_id)
    return templates.TemplateResponse(
        "client_edit.html", {"request": request, "client": client}
    )


@app.post("/clients/{client_id}/edit")
def update_client(
    client_id: int,
    name: str = Form(...),
    address: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
) -> RedirectResponse:
    """Process client edit form and update the database."""
    fetch_client(client_id)  # ensure exists
    with get_connection() as conn:
        conn.execute(
            "UPDATE clients SET name = ?, address = ?, phone = ?, email = ? WHERE id = ?",
            (name.strip(), address.strip(), phone.strip(), email.strip(), client_id),
        )
        conn.commit()
    return RedirectResponse(url=f"/clients/{client_id}", status_code=303)


@app.post("/clients/{client_id}/delete")
def delete_client(client_id: int) -> RedirectResponse:
    """Delete a client. Fails if client has any jobs."""
    fetch_client(client_id)
    with get_connection() as conn:
        job_count = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE client_id = ?", (client_id,)
        ).fetchone()[0]
    if job_count > 0:
        return RedirectResponse(
            url=f"/clients/{client_id}?error=has_jobs", status_code=303
        )
    with get_connection() as conn:
        conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))
        conn.commit()
    return RedirectResponse(url="/clients", status_code=303)


# ----- Crews -----
@app.get("/crews/new", response_class=HTMLResponse)
def new_crew_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("crew_form.html", {"request": request})


@app.post("/crews/new")
def create_crew(name: str = Form(...)) -> RedirectResponse:
    with get_connection() as conn:
        conn.execute("INSERT INTO crews (name) VALUES (?)", (name.strip(),))
        conn.commit()
        rid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()[0]
    return RedirectResponse(url=f"/crews/{rid}", status_code=303)


def fetch_crew(crew_id: int) -> sqlite3.Row:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM crews WHERE id = ?", (crew_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Crew not found")
    return row


@app.get("/crews/{crew_id}", response_class=HTMLResponse)
def view_crew(crew_id: int, request: Request) -> HTMLResponse:
    crew = fetch_crew(crew_id)
    with get_connection() as conn:
        jobs = conn.execute(
            "SELECT id, description, scheduled_date, status FROM jobs WHERE crew_id = ? ORDER BY datetime(scheduled_date) DESC",
            (crew_id,),
        ).fetchall()
    return templates.TemplateResponse(
        "crew_detail.html", {"request": request, "crew": crew, "jobs": jobs}
    )


@app.get("/crews/{crew_id}/edit", response_class=HTMLResponse)
def edit_crew_form(crew_id: int, request: Request) -> HTMLResponse:
    crew = fetch_crew(crew_id)
    return templates.TemplateResponse("crew_edit.html", {"request": request, "crew": crew})


@app.post("/crews/{crew_id}/edit")
def update_crew(crew_id: int, name: str = Form(...)) -> RedirectResponse:
    fetch_crew(crew_id)
    with get_connection() as conn:
        conn.execute("UPDATE crews SET name = ? WHERE id = ?", (name.strip(), crew_id))
        conn.commit()
    return RedirectResponse(url=f"/crews/{crew_id}", status_code=303)


@app.post("/crews/{crew_id}/delete")
def delete_crew(crew_id: int) -> RedirectResponse:
    fetch_crew(crew_id)
    with get_connection() as conn:
        conn.execute("UPDATE jobs SET crew_id = NULL WHERE crew_id = ?", (crew_id,))
        conn.commit()
        conn.execute("DELETE FROM crews WHERE id = ?", (crew_id,))
        conn.commit()
    return RedirectResponse(url="/crews", status_code=303)


# ----- Members -----
@app.get("/members/new", response_class=HTMLResponse)
def new_member_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("member_form.html", {"request": request})


@app.post("/members/new")
def create_member(name: str = Form(...)) -> RedirectResponse:
    with get_connection() as conn:
        conn.execute("INSERT INTO members (name) VALUES (?)", (name.strip(),))
        conn.commit()
        mid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()[0]
    return RedirectResponse(url=f"/members/{mid}", status_code=303)


def fetch_member(member_id: int) -> sqlite3.Row:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return row


@app.get("/members/{member_id}", response_class=HTMLResponse)
def view_member(member_id: int, request: Request) -> HTMLResponse:
    member = fetch_member(member_id)
    with get_connection() as conn:
        jobs = conn.execute(
            """
            SELECT jobs.id, jobs.description, jobs.scheduled_date, jobs.status
            FROM jobs
            JOIN job_members ON job_members.job_id = jobs.id
            WHERE job_members.member_id = ?
            ORDER BY datetime(jobs.scheduled_date) DESC
            """,
            (member_id,),
        ).fetchall()
    return templates.TemplateResponse(
        "member_detail.html", {"request": request, "member": member, "jobs": jobs}
    )


@app.get("/members/{member_id}/edit", response_class=HTMLResponse)
def edit_member_form(member_id: int, request: Request) -> HTMLResponse:
    member = fetch_member(member_id)
    return templates.TemplateResponse("member_edit.html", {"request": request, "member": member})


@app.post("/members/{member_id}/edit")
def update_member(member_id: int, name: str = Form(...)) -> RedirectResponse:
    fetch_member(member_id)
    with get_connection() as conn:
        conn.execute("UPDATE members SET name = ? WHERE id = ?", (name.strip(), member_id))
        conn.commit()
    return RedirectResponse(url=f"/members/{member_id}", status_code=303)


@app.post("/members/{member_id}/delete")
def delete_member(member_id: int) -> RedirectResponse:
    fetch_member(member_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM job_members WHERE member_id = ?", (member_id,))
        conn.commit()
        conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
        conn.commit()
    return RedirectResponse(url="/members", status_code=303)


def fetch_quote(quote_id: int) -> sqlite3.Row:
    """Fetch a quote by ID with client name, raising 404 if not found."""
    with get_connection() as conn:
        quote = conn.execute(
            """
            SELECT quotes.*, clients.name as client_name, clients.address as client_address,
                   clients.phone as client_phone, clients.email as client_email
            FROM quotes
            JOIN clients ON quotes.client_id = clients.id
            WHERE quotes.id = ?
            """,
            (quote_id,),
        ).fetchone()
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote


@app.get("/quotes", response_class=HTMLResponse)
def list_quotes(request: Request, status: Optional[str] = None) -> HTMLResponse:
    """List all quotes, optionally filtered by status."""
    with get_connection() as conn:
        if status and status in ("Draft", "Sent", "Accepted", "Declined"):
            quotes = conn.execute(
                """
                SELECT quotes.*, clients.name as client_name
                FROM quotes JOIN clients ON quotes.client_id = clients.id
                WHERE quotes.status = ? ORDER BY quotes.created_at DESC
                """,
                (status,),
            ).fetchall()
        else:
            quotes = conn.execute(
                """
                SELECT quotes.*, clients.name as client_name
                FROM quotes JOIN clients ON quotes.client_id = clients.id
                ORDER BY quotes.created_at DESC
                """
            ).fetchall()
    return templates.TemplateResponse(
        "quotes.html",
        {"request": request, "quotes": quotes, "filter_status": status},
    )


@app.get("/quotes/new", response_class=HTMLResponse)
def new_quote_form(request: Request) -> HTMLResponse:
    """Display form to create a new quote."""
    with get_connection() as conn:
        clients = conn.execute("SELECT id, name FROM clients ORDER BY name").fetchall()
    return templates.TemplateResponse(
        "quote_form.html", {"request": request, "clients": clients}
    )


@app.post("/quotes/new")
def create_quote(
    client_id: int = Form(...),
    description: str = Form(...),
    estimated_hours: float = Form(...),
    estimated_cost: float = Form(...),
    valid_until: str = Form(""),
) -> RedirectResponse:
    """Create a new quote."""
    fetch_client(client_id)
    created_at = datetime.utcnow().isoformat() + "Z"
    valid_until_val = valid_until.strip() or None
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO quotes (client_id, description, estimated_hours, estimated_cost, status, created_at, valid_until)
            VALUES (?, ?, ?, ?, 'Draft', ?, ?)
            """,
            (client_id, description.strip(), estimated_hours, estimated_cost, created_at, valid_until_val),
        )
        conn.commit()
        qid = conn.execute("SELECT last_insert_rowid() AS id").fetchone()[0]
    return RedirectResponse(url=f"/quotes/{qid}", status_code=303)


@app.get("/quotes/{quote_id}", response_class=HTMLResponse)
def view_quote(quote_id: int, request: Request) -> HTMLResponse:
    """View a single quote (read-only). Accept button shown when status is Draft or Sent."""
    quote = fetch_quote(quote_id)
    return templates.TemplateResponse(
        "quote_detail.html", {"request": request, "quote": quote}
    )


@app.post("/quotes/{quote_id}/accept")
def accept_quote(quote_id: int) -> RedirectResponse:
    """Create a job from the quote and mark quote as Accepted."""
    quote = fetch_quote(quote_id)
    if quote["status"] == "Accepted":
        return RedirectResponse(url=f"/jobs/{quote['job_id']}", status_code=303)
    if quote["status"] == "Declined":
        raise HTTPException(status_code=400, detail="Cannot accept a declined quote")
    # Create job with scheduled_date = now (user can edit)
    scheduled_date = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (client_id, description, scheduled_date, crew, crew_id, estimated_hours, estimated_cost, status)
            VALUES (?, ?, ?, '', NULL, ?, ?, 'Scheduled')
            """,
            (quote["client_id"], quote["description"], scheduled_date, quote["estimated_hours"], quote["estimated_cost"]),
        )
        conn.commit()
        job_row = conn.execute("SELECT id FROM jobs ORDER BY id DESC LIMIT 1").fetchone()
        job_id = job_row["id"]
        conn.execute(
            "UPDATE quotes SET status = 'Accepted', job_id = ? WHERE id = ?",
            (job_id, quote_id),
        )
        conn.commit()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/quotes/{quote_id}/decline")
def decline_quote(quote_id: int) -> RedirectResponse:
    """Mark quote as Declined."""
    quote = fetch_quote(quote_id)
    if quote["status"] not in ("Draft", "Sent"):
        raise HTTPException(status_code=400, detail="Quote already accepted or declined")
    with get_connection() as conn:
        conn.execute("UPDATE quotes SET status = 'Declined' WHERE id = ?", (quote_id,))
        conn.commit()
    return RedirectResponse(url=f"/quotes/{quote_id}", status_code=303)


@app.post("/quotes/{quote_id}/send")
def send_quote(quote_id: int) -> RedirectResponse:
    """Mark quote as Sent."""
    quote = fetch_quote(quote_id)
    if quote["status"] != "Draft":
        raise HTTPException(status_code=400, detail="Only draft quotes can be marked as sent")
    with get_connection() as conn:
        conn.execute("UPDATE quotes SET status = 'Sent' WHERE id = ?", (quote_id,))
        conn.commit()
    return RedirectResponse(url=f"/quotes/{quote_id}", status_code=303)


@app.get("/jobs", response_class=HTMLResponse)
def list_jobs(request: Request) -> HTMLResponse:
    """List all jobs with client names and statuses."""
    with get_connection() as conn:
        jobs = conn.execute(
            """
            SELECT jobs.*, clients.name as client_name
            FROM jobs
            JOIN clients ON jobs.client_id = clients.id
            ORDER BY datetime(scheduled_date) ASC
            """
        ).fetchall()
    return templates.TemplateResponse(
        "jobs.html", {"request": request, "jobs": jobs}
    )


@app.get("/jobs/calendar", response_class=HTMLResponse)
def jobs_calendar(request: Request, year: Optional[int] = None, month: Optional[int] = None) -> HTMLResponse:
    """Calendar view of jobs by month."""
    now = datetime.utcnow()
    y = year if year is not None else now.year
    m = month if month is not None else now.month
    # Clamp month
    if m < 1:
        m, y = 12, y - 1
    elif m > 12:
        m, y = 1, y + 1
    first_day, last_day = calendar.monthrange(y, m)
    start = f"{y}-{m:02d}-01"
    end = f"{y}-{m:02d}-{last_day:02d}"
    with get_connection() as conn:
        jobs = conn.execute(
            """
            SELECT jobs.id, jobs.description, jobs.scheduled_date, jobs.status, clients.name as client_name
            FROM jobs
            JOIN clients ON jobs.client_id = clients.id
            WHERE date(jobs.scheduled_date) >= date(?) AND date(jobs.scheduled_date) <= date(?)
            ORDER BY datetime(jobs.scheduled_date)
            """,
            (start, end),
        ).fetchall()
    jobs_by_date = {}
    for j in jobs:
        key = j["scheduled_date"][:10] if j["scheduled_date"] else None
        if key:
            jobs_by_date.setdefault(key, []).append(j)
    prev_m, prev_y = (m - 1, y) if m > 1 else (12, y - 1)
    next_m, next_y = (m + 1, y) if m < 12 else (1, y + 1)
    month_name = calendar.month_name[m]
    return templates.TemplateResponse(
        "jobs_calendar.html",
        {
            "request": request,
            "year": y,
            "month": m,
            "month_name": month_name,
            "jobs_by_date": jobs_by_date,
            "prev_year": prev_y,
            "prev_month": prev_m,
            "next_year": next_y,
            "next_month": next_m,
            "calendar_grid": calendar.monthcalendar(y, m),
            "today": now,
        },
    )


@app.post("/jobs/{job_id}/notify_customer")
def notify_customer(job_id: int) -> RedirectResponse:
    """Set 'On my way' notification timestamp for the job."""
    job = fetch_job(job_id)
    notified_at = datetime.utcnow().isoformat() + "Z"
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET on_my_way_sent_at = ? WHERE id = ?",
            (notified_at, job_id),
        )
        conn.commit()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/new", response_class=HTMLResponse)
def new_job_form(request: Request) -> HTMLResponse:
    """Display a form for creating a new job."""
    with get_connection() as conn:
        clients = conn.execute("SELECT id, name FROM clients ORDER BY name").fetchall()
        crews = conn.execute("SELECT id, name FROM crews ORDER BY name").fetchall()
        members = conn.execute("SELECT id, name FROM members ORDER BY name").fetchall()
    return templates.TemplateResponse(
        "job_form.html",
        {"request": request, "clients": clients, "crews": crews, "members": members},
    )


@app.post("/jobs/new")
def create_job(
    client_id: int = Form(...),
    description: str = Form(...),
    scheduled_date: str = Form(...),
    crew: str = Form(""),
    crew_id: Optional[int] = Form(None),
    member_ids: Optional[List[int]] = Form(None),
    estimated_hours: float = Form(...),
    estimated_cost: float = Form(...),
) -> RedirectResponse:
    """Process the new job form and insert the job into the database."""
    try:
        dt = datetime.fromisoformat(scheduled_date)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid date: {err}")
    member_ids = member_ids or []
    cid = int(crew_id) if crew_id and str(crew_id).strip() else None
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (client_id, description, scheduled_date, crew, crew_id, estimated_hours, estimated_cost)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (client_id, description.strip(), dt.isoformat(), crew.strip(), cid, estimated_hours, estimated_cost),
        )
        conn.commit()
        job_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()[0]
        for mid in member_ids:
            conn.execute("INSERT INTO job_members (job_id, member_id) VALUES (?, ?)", (job_id, mid))
        conn.commit()
    return RedirectResponse(url="/jobs", status_code=303)


@app.get("/jobs/{job_id}/edit", response_class=HTMLResponse)
def edit_job_form(job_id: int, request: Request) -> HTMLResponse:
    """Display form to edit a job. Redirects to job detail if job is Completed."""
    job = fetch_job(job_id)
    if job["status"] == "Completed":
        return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)
    with get_connection() as conn:
        clients = conn.execute("SELECT id, name FROM clients ORDER BY name").fetchall()
        crews = conn.execute("SELECT id, name FROM crews ORDER BY name").fetchall()
        members = conn.execute("SELECT id, name FROM members ORDER BY name").fetchall()
        job_member_ids = [
            r[0]
            for r in conn.execute(
                "SELECT member_id FROM job_members WHERE job_id = ?", (job_id,)
            ).fetchall()
        ]
    return templates.TemplateResponse(
        "job_edit.html",
        {
            "request": request,
            "job": job,
            "clients": clients,
            "crews": crews,
            "members": members,
            "job_member_ids": job_member_ids,
        },
    )


@app.post("/jobs/{job_id}/edit")
def update_job(
    job_id: int,
    client_id: int = Form(...),
    description: str = Form(...),
    scheduled_date: str = Form(...),
    crew: str = Form(""),
    crew_id: Optional[int] = Form(None),
    member_ids: Optional[List[int]] = Form(None),
    estimated_hours: float = Form(...),
    estimated_cost: float = Form(...),
) -> RedirectResponse:
    """Process job edit form. Refuses to update if job is Completed."""
    job = fetch_job(job_id)
    if job["status"] == "Completed":
        raise HTTPException(status_code=400, detail="Cannot edit a completed job")
    try:
        dt = datetime.fromisoformat(scheduled_date)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=f"Invalid date: {err}")
    member_ids = member_ids or []
    cid = int(crew_id) if crew_id and str(crew_id).strip() else None
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET client_id = ?, description = ?, scheduled_date = ?, crew = ?, crew_id = ?,
                estimated_hours = ?, estimated_cost = ?
            WHERE id = ?
            """,
            (
                client_id,
                description.strip(),
                dt.isoformat(),
                crew.strip(),
                cid,
                estimated_hours,
                estimated_cost,
                job_id,
            ),
        )
        conn.execute("DELETE FROM job_members WHERE job_id = ?", (job_id,))
        for mid in member_ids:
            conn.execute("INSERT INTO job_members (job_id, member_id) VALUES (?, ?)", (job_id, mid))
        conn.commit()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


def fetch_job(job_id: int) -> sqlite3.Row:
    """Fetch a job by ID, raising a 404 if not found."""
    with get_connection() as conn:
        job = conn.execute(
            """
            SELECT jobs.*, clients.name as client_name, clients.address as client_address,
                   clients.phone as client_phone, clients.email as client_email,
                   crews.name as crew_name
            FROM jobs
            JOIN clients ON jobs.client_id = clients.id
            LEFT JOIN crews ON jobs.crew_id = crews.id
            WHERE jobs.id = ?
            """,
            (job_id,),
        ).fetchone()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def view_job(job_id: int, request: Request) -> HTMLResponse:
    """Display details for a single job, including tasks and update forms."""
    job = fetch_job(job_id)
    with get_connection() as conn:
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
        job_members = conn.execute(
            """
            SELECT members.id, members.name FROM members
            JOIN job_members ON job_members.member_id = members.id
            WHERE job_members.job_id = ?
            ORDER BY members.name
            """,
            (job_id,),
        ).fetchall()
    return templates.TemplateResponse(
        "job_detail.html",
        {
            "request": request,
            "job": job,
            "tasks": tasks,
            "job_members": job_members,
            "weasyprint": _WEASYPRINT_AVAILABLE,
        },
    )


@app.post("/jobs/{job_id}/add_task")
def add_task(job_id: int, description: str = Form(...)) -> RedirectResponse:
    """Add a new task to a job."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (job_id, description) VALUES (?, ?)",
            (job_id, description.strip()),
        )
        conn.commit()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/tasks/{task_id}/toggle")
def toggle_task(task_id: int) -> RedirectResponse:
    """Toggle the completion status of a task.

    The task's `completed` field is flipped between 0 and 1.  The user
    is redirected back to the job detail page.
    """
    with get_connection() as conn:
        task = conn.execute(
            "SELECT job_id, completed FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        new_completed = 0 if task["completed"] else 1
        conn.execute(
            "UPDATE tasks SET completed = ? WHERE id = ?", (new_completed, task_id)
        )
        conn.commit()
    return RedirectResponse(url=f"/jobs/{task['job_id']}", status_code=303)


@app.post("/jobs/{job_id}/update_status")
def update_job_status(job_id: int, status: str = Form(...)) -> RedirectResponse:
    """Update the status of a job."""
    allowed_statuses = {"Scheduled", "In progress", "Completed"}
    if status not in allowed_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status = ? WHERE id = ?", (status, job_id)
        )
        conn.commit()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/complete")
def complete_job(
    job_id: int,
    actual_hours: float = Form(...),
    actual_cost: float = Form(...),
    status: str = Form("Completed"),
) -> RedirectResponse:
    """Mark a job as completed and record actual hours and cost."""
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, actual_hours = ?, actual_cost = ?
            WHERE id = ?
            """,
            (status, actual_hours, actual_cost, job_id),
        )
        conn.commit()
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/mark_invoice_sent")
def mark_invoice_sent(job_id: int) -> RedirectResponse:
    """Mark the job's invoice as sent."""
    job = fetch_job(job_id)
    if job["status"] != "Completed":
        raise HTTPException(status_code=400, detail="Job must be completed first")
    sent_at = datetime.utcnow().isoformat() + "Z"
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET invoice_sent_at = ?, invoice_status = 'Sent' WHERE id = ?",
            (sent_at, job_id),
        )
        conn.commit()
    return RedirectResponse(url=f"/jobs/{job_id}/invoice", status_code=303)


@app.post("/jobs/{job_id}/payments")
def add_payment(
    job_id: int,
    amount: float = Form(...),
    method: str = Form(...),
) -> RedirectResponse:
    """Record a payment for a completed job."""
    job = fetch_job(job_id)
    if job["status"] != "Completed":
        raise HTTPException(status_code=400, detail="Job must be completed first")
    allowed_methods = ("Cash", "Check", "Card", "Other")
    if method not in allowed_methods:
        raise HTTPException(status_code=400, detail="Invalid payment method")
    paid_at = datetime.utcnow().isoformat() + "Z"
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO payments (job_id, amount, method, paid_at) VALUES (?, ?, ?, ?)",
            (job_id, amount, method, paid_at),
        )
        conn.commit()
        total = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE job_id = ?", (job_id,)
        ).fetchone()[0]
        actual_cost = float(job["actual_cost"] or 0)
        if total >= actual_cost:
            conn.execute(
                "UPDATE jobs SET invoice_status = 'Paid', paid_at = ? WHERE id = ?",
                (paid_at, job_id),
            )
            conn.commit()
    return RedirectResponse(url=f"/jobs/{job_id}/invoice", status_code=303)


@app.get("/jobs/{job_id}/invoice", response_class=HTMLResponse)
def view_invoice(job_id: int, request: Request) -> HTMLResponse:
    """Render an invoice for a completed job.

    If WeasyPrint is installed, the user is offered the option to download a PDF.
    """
    job = fetch_job(job_id)
    if job["status"] != "Completed":
        raise HTTPException(status_code=400, detail="Job must be completed before invoicing")
    with get_connection() as conn:
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
        payments = conn.execute(
            "SELECT * FROM payments WHERE job_id = ? ORDER BY paid_at", (job_id,)
        ).fetchall()
        total_paid = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE job_id = ?", (job_id,)
        ).fetchone()[0]
    return templates.TemplateResponse(
        "invoice.html",
        {
            "request": request,
            "job": job,
            "tasks": tasks,
            "payments": payments,
            "total_paid": total_paid,
            "weasyprint": _WEASYPRINT_AVAILABLE,
        },
    )


@app.get("/jobs/{job_id}/invoice.pdf")
def download_invoice_pdf(job_id: int) -> Response:
    """Generate and return a PDF invoice for a completed job.

    Requires WeasyPrint to be installed.  Otherwise returns 501.
    """
    if not _WEASYPRINT_AVAILABLE:
        raise HTTPException(status_code=501, detail="PDF generation not available")
    job = fetch_job(job_id)
    if job["status"] != "Completed":
        raise HTTPException(status_code=400, detail="Job must be completed before invoicing")
    with get_connection() as conn:
        tasks = conn.execute(
            "SELECT * FROM tasks WHERE job_id = ? ORDER BY id", (job_id,)
        ).fetchall()
    # Render invoice HTML into string using templates
    # We use `require_self` to ensure relative asset links are included; we pass
    # the Jinja2 template to render into HTML string.
    from fastapi import BackgroundTasks
    html_content = templates.get_template("invoice_pdf.html").render(
        job=job, tasks=tasks
    )
    # Use WeasyPrint to convert to PDF
    pdf = _WeasyHTML(string=html_content, base_url=str(os.path.dirname(__file__))).write_pdf()
    headers = {"Content-Disposition": f"attachment; filename=invoice_{job_id}.pdf"}
    return Response(content=pdf, media_type="application/pdf", headers=headers)


@app.exception_handler(HTTPException)
def http_exception_handler(request: Request, exc: HTTPException):
    """Return HTML 404 page instead of JSON when a resource is not found."""
    if exc.status_code == 404:
        return templates.TemplateResponse(
            "404.html", {"request": request}, status_code=404
        )
    return JSONResponse(content={"detail": exc.detail}, status_code=exc.status_code)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "5050"))
    host = "0.0.0.0"  # listen on all interfaces so browser can connect
    print(f"\n  Landscaping App:  http://localhost:{port}/\n")
    uvicorn.run("app:app", host=host, port=port, reload=False)
