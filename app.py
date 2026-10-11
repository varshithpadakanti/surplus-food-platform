import os
import sqlite3
from functools import wraps
from datetime import date

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import SCHEMA, seed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Vercel's filesystem is read-only except /tmp (and /tmp is NOT permanent).
IS_VERCEL = bool(os.environ.get("VERCEL"))
DB_PATH = "/tmp/surplus.db" if IS_VERCEL else os.path.join(BASE_DIR, "surplus.db")

# static_folder="public" -> works locally; on Vercel the CDN serves /public.
app = Flask(__name__, static_folder="public", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")


# ---------- database ----------
def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    empty = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
    if empty and os.environ.get("SEED_DEMO", "1") == "1":
        seed(conn)
    conn.commit()
    conn.close()


init_db()


# ---------- auth helpers ----------
@app.before_request
def load_user():
    uid = session.get("user_id")
    g.user = None
    if uid:
        g.user = get_db().execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if g.user is None:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped


def role_required(role):
    def deco(view):
        @wraps(view)
        @login_required
        def wrapped(*a, **kw):
            if g.user["role"] != role:
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco


@app.template_filter("days_left")
def days_left(iso):
    d = (date.fromisoformat(iso) - date.today()).days
    if d < 0:
        return "expired"
    return "expires today" if d == 0 else f"{d} day{'s' if d != 1 else ''} left"


def get_stats(db):
    r = db.execute("""
        SELECT COUNT(*)                                             AS total,
               COALESCE(SUM(status = 'available'), 0)               AS available,
               COALESCE(SUM(status = 'reserved'), 0)                AS reserved,
               COALESCE(SUM(status = 'collected'), 0)               AS collected
        FROM donations""").fetchone()
    return dict(r)


# ---------- public pages ----------
@app.route("/")
def index():
    return render_template("index.html", stats=get_stats(get_db()))


@app.route("/api/stats")
def api_stats():
    return jsonify(get_stats(get_db()))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "")
        city = request.form.get("city", "").strip()
        if not (name and email and city) or role not in ("donor", "ngo") or len(password) < 6:
            flash("Fill in every field. Password needs at least 6 characters.", "error")
        else:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users(name, email, password_hash, role, city) VALUES (?,?,?,?,?)",
                    (name, email, generate_password_hash(password), role, city))
                db.commit()
                flash("Account created. Log in to continue.", "ok")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Wrong email or password.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------- donations ----------
@app.route("/donations")
def donations():
    db = get_db()
    q = request.args.get("q", "").strip()
    sql = """SELECT d.*, u.name AS donor_name, u.city
             FROM donations d JOIN users u ON u.id = d.donor_id
             WHERE d.status = 'available' AND d.expiry_date >= date('now')"""
    params = []
    if q:
        sql += " AND (d.food_item LIKE ? OR u.city LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY d.expiry_date ASC, d.id DESC LIMIT 100"
    rows = db.execute(sql, params).fetchall()
    requested = set()
    if g.user and g.user["role"] == "ngo":
        requested = {r["donation_id"] for r in db.execute(
            "SELECT donation_id FROM requests WHERE ngo_id = ?", (g.user["id"],))}
    return render_template("donations.html", rows=rows, q=q, requested=requested)


@app.route("/donations/new", methods=["GET", "POST"])
@role_required("donor")
def new_donation():
    if request.method == "POST":
        f = request.form
        try:
            qty = int(f.get("quantity", "0"))
            date.fromisoformat(f.get("expiry_date", ""))
        except ValueError:
            qty = 0
        if not f.get("food_item", "").strip() or qty <= 0 or not f.get("pickup_address", "").strip():
            flash("Check the form: item, quantity, address and a valid expiry date are required.", "error")
        else:
            db = get_db()
            db.execute(
                """INSERT INTO donations(donor_id, food_item, quantity, unit, pickup_address, expiry_date)
                   VALUES (?,?,?,?,?,?)""",
                (g.user["id"], f["food_item"].strip(), qty, f.get("unit", "kg"),
                 f["pickup_address"].strip(), f["expiry_date"]))
            db.commit()
            flash("Donation listed. NGOs can request it now.", "ok")
            return redirect(url_for("dashboard"))
    return render_template("new_donation.html", today=date.today().isoformat())


@app.post("/donations/<int:did>/request")
@role_required("ngo")
def request_donation(did):
    db = get_db()
    d = db.execute("SELECT * FROM donations WHERE id = ?", (did,)).fetchone()
    if not d or d["status"] != "available":
        flash("That donation is no longer available.", "error")
    else:
        try:
            db.execute("INSERT INTO requests(donation_id, ngo_id, note) VALUES (?,?,?)",
                       (did, g.user["id"], request.form.get("note", "").strip()[:200]))
            db.commit()
            flash("Request sent to the donor.", "ok")
        except sqlite3.IntegrityError:
            flash("You already requested this donation.", "error")
    return redirect(url_for("donations"))


@app.post("/requests/<int:rid>/<action>")
@role_required("donor")
def update_request(rid, action):
    db = get_db()
    r = db.execute("""SELECT r.*, d.donor_id, d.status AS dstatus
                      FROM requests r JOIN donations d ON d.id = r.donation_id
                      WHERE r.id = ?""", (rid,)).fetchone()
    if not r or r["donor_id"] != g.user["id"]:
        abort(404)
    if action == "approve" and r["status"] == "pending" and r["dstatus"] == "available":
        db.execute("UPDATE requests SET status='approved' WHERE id=?", (rid,))
        db.execute("UPDATE requests SET status='rejected' WHERE donation_id=? AND id!=? AND status='pending'",
                   (r["donation_id"], rid))
        db.execute("UPDATE donations SET status='reserved' WHERE id=?", (r["donation_id"],))
    elif action == "reject" and r["status"] == "pending":
        db.execute("UPDATE requests SET status='rejected' WHERE id=?", (rid,))
    elif action == "collect" and r["status"] == "approved":
        db.execute("UPDATE requests SET status='collected' WHERE id=?", (rid,))
        db.execute("UPDATE donations SET status='collected' WHERE id=?", (r["donation_id"],))
    else:
        flash("That action isn't possible right now.", "error")
        return redirect(url_for("dashboard"))
    db.commit()
    flash("Updated.", "ok")
    return redirect(url_for("dashboard"))


# ---------- dashboard ----------
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    if g.user["role"] == "donor":
        donations = [dict(r) for r in db.execute(
            "SELECT * FROM donations WHERE donor_id=? ORDER BY id DESC LIMIT 50", (g.user["id"],))]
        reqs = db.execute("""
            SELECT r.*, u.name AS ngo_name, u.city AS ngo_city FROM requests r
            JOIN users u ON u.id = r.ngo_id
            WHERE r.donation_id IN (SELECT id FROM donations WHERE donor_id=?)
            ORDER BY r.id""", (g.user["id"],)).fetchall()
        by_donation = {}
        for r in reqs:
            by_donation.setdefault(r["donation_id"], []).append(dict(r))
        for d in donations:
            d["requests"] = by_donation.get(d["id"], [])
        return render_template("dashboard_donor.html", donations=donations)
    rows = db.execute("""
        SELECT r.*, d.food_item, d.quantity, d.unit, d.pickup_address, d.expiry_date,
               u.name AS donor_name
        FROM requests r JOIN donations d ON d.id = r.donation_id
        JOIN users u ON u.id = d.donor_id
        WHERE r.ngo_id = ? ORDER BY r.id DESC LIMIT 50""", (g.user["id"],)).fetchall()
    return render_template("dashboard_ngo.html", rows=rows)


if __name__ == "__main__":
    app.run(debug=True)
