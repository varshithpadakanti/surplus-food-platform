# Surplus Food Reduction Platform
Flask + HTML/CSS + SQLite. Donors list surplus food, NGOs request it, donors approve and mark pickup.

## Run locally
    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    python app.py        # http://127.0.0.1:5000

Demo logins (password demo1234): donor@demo.com, ngo@demo.com. Set SEED_DEMO=0 to start empty.

## Vercel
Environment variable: SECRET_KEY (any long random string).
Note: on Vercel the SQLite file lives in /tmp and resets. Use a hosted database for permanent data.
