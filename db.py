"""Database schema + demo seed data (SQLite, normalized to 3NF)."""
import random
from datetime import date, timedelta
from werkzeug.security import generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('donor', 'ngo')),
    city          TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS donations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    donor_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    food_item      TEXT NOT NULL,
    quantity       INTEGER NOT NULL CHECK (quantity > 0),
    unit           TEXT NOT NULL DEFAULT 'kg',
    pickup_address TEXT NOT NULL,
    expiry_date    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'available'
                   CHECK (status IN ('available', 'reserved', 'collected')),
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS requests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    donation_id INTEGER NOT NULL REFERENCES donations(id) ON DELETE CASCADE,
    ngo_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status      TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'collected')),
    note        TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (donation_id, ngo_id)
);

CREATE INDEX IF NOT EXISTS idx_donations_status  ON donations(status, expiry_date);
CREATE INDEX IF NOT EXISTS idx_donations_donor   ON donations(donor_id);
CREATE INDEX IF NOT EXISTS idx_requests_ngo      ON requests(ngo_id);
CREATE INDEX IF NOT EXISTS idx_requests_donation ON requests(donation_id);
"""

CITIES = ["Hyderabad", "Bengaluru", "Chennai", "Mumbai", "Pune"]
DONORS = ["Spice Route Kitchen", "Green Leaf Caterers", "Daily Bread Bakery",
          "Grand Palace Banquets", "Fresh Basket Mart", "Campus Mess Hall"]
NGOS = ["Annadaan Foundation", "Hunger Free Trust", "Shelter of Hope",
        "Robin Hood Army Chapter", "Seva Kitchen"]
FOODS = [("Cooked rice", "kg"), ("Vegetable curry", "kg"), ("Bread loaves", "pcs"),
         ("Fresh vegetables", "kg"), ("Fruit boxes", "boxes"), ("Dal", "kg"),
         ("Packed meals", "pcs"), ("Milk packets", "pcs"), ("Chapatis", "pcs")]


def seed(db, n_donations=110):
    """Insert demo accounts and ~110 sample donations. Demo password: demo1234"""
    random.seed(7)
    pw = generate_password_hash("demo1234")

    def add_user(name, email, role, city):
        return db.execute(
            "INSERT INTO users(name, email, password_hash, role, city) VALUES (?,?,?,?,?)",
            (name, email, pw, role, city)).lastrowid

    donors = [add_user("Demo Restaurant", "donor@demo.com", "donor", "Hyderabad")]
    ngos = [add_user("Demo NGO", "ngo@demo.com", "ngo", "Hyderabad")]
    for i, name in enumerate(DONORS):
        donors.append(add_user(name, f"donor{i}@example.com", "donor", random.choice(CITIES)))
    for i, name in enumerate(NGOS):
        ngos.append(add_user(name, f"ngo{i}@example.com", "ngo", random.choice(CITIES)))

    today = date.today()
    for i in range(n_donations):
        food, unit = random.choice(FOODS)
        status = random.choices(["available", "reserved", "collected"], [5, 2, 3])[0]
        expiry = today + timedelta(days=random.randint(0, 5) if status == "available"
                                   else random.randint(-3, 1))
        donor = random.choice(donors)
        did = db.execute(
            """INSERT INTO donations(donor_id, food_item, quantity, unit, pickup_address, expiry_date, status)
               VALUES (?,?,?,?,?,?,?)""",
            (donor, food, random.randint(2, 40), unit,
             f"{random.randint(1, 99)}, Main Road, {random.choice(CITIES)}",
             expiry.isoformat(), status)).lastrowid
        if status == "reserved":
            db.execute("INSERT INTO requests(donation_id, ngo_id, status) VALUES (?,?,'approved')",
                       (did, random.choice(ngos)))
        elif status == "collected":
            db.execute("INSERT INTO requests(donation_id, ngo_id, status) VALUES (?,?,'collected')",
                       (did, random.choice(ngos)))
        elif random.random() < 0.25:
            db.execute("INSERT INTO requests(donation_id, ngo_id, status) VALUES (?,?,'pending')",
                       (did, random.choice(ngos)))
