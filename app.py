"""
Gym Session Tracker — Playwright edition
Supports JS-heavy sites (Mariana Tek, Bsport, custom React apps).
"""

import sqlite3
import smtplib
import logging
import os
import re
import asyncio
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import numpy as np
from flask import Flask, render_template_string, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from playwright.async_api import async_playwright

from config import GYMS, EMAIL_CONFIG, ALERT_CONFIG

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/opt/render/project/src"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "gym_tracker.db"

# ── Database ──────────────────────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gym_id TEXT NOT NULL, session_id TEXT NOT NULL,
            coach TEXT, title TEXT, starts_at TEXT, capacity INTEGER,
            UNIQUE(gym_id, session_id)
        );
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gym_id TEXT NOT NULL, session_id TEXT NOT NULL,
            captured_at TEXT NOT NULL, spots_left INTEGER, is_full INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS alerts_sent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gym_id TEXT NOT NULL, session_id TEXT NOT NULL,
            alert_type TEXT NOT NULL, sent_at TEXT NOT NULL
        );
    """)
    con.commit(); con.close()
    log.info(f"Database ready at {DB_PATH}")

def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

# ── Scraping with Playwright ──────────────────────────────────────────────────
def parse_spots(text: str):
    if not text: return None
    text = text.lower().strip()
    if any(w in text for w in ["complet", "full", "sold out", "no spots", "0 place", "waitlist", "liste d'attente"]):
        return 0
    m = re.search(r"(\d+)\s*(place|spot|pl |seat)", text)
    if m: return int(m.group(1))
    m = re.search(r"(\d+)", text)
    if m: return int(m.group(1))
    return None

def make_session_id(title, starts_at, coach):
    return re.sub(r"\W+", "_", f"{title}_{starts_at}_{coach}").lower()[:80]

async def scrape_gym_playwright(gym: dict) -> list:
    """Scrape a single gym using a real Chromium browser."""
    sessions = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36"
        )
        try:
            log.info(f"[{gym['id']}] Navigating to {gym['url']}")
            await page.goto(gym["url"], wait_until="networkidle", timeout=45000)

            # Wait for session blocks to appear
            wait_sel = gym.get("wait_for_selector", gym.get("session_selector", "body"))
            try:
                await page.wait_for_selector(wait_sel, timeout=20000)
            except Exception:
                log.warning(f"[{gym['id']}] Timeout waiting for selector '{wait_sel}'")

            # Extra wait if configured (some sites load lazily)
            extra_wait = gym.get("extra_wait_ms", 0)
            if extra_wait:
                await page.wait_for_timeout(extra_wait)

            blocks = await page.query_selector_all(gym.get("session_selector", ""))
            log.info(f"[{gym['id']}] Found {len(blocks)} session blocks")

            for block in blocks:
                try:
                    s = {
                        "title": "", "coach": "", "starts_at": "",
                        "capacity": gym.get("default_capacity"),
                        "spots_left": None, "is_full": False
                    }
                    for field in ["title", "coach", "starts_at"]:
                        sel = gym.get(f"{field}_selector")
                        if sel:
                            el = await block.query_selector(sel)
                            s[field] = (await el.inner_text()).strip() if el else ""

                    if gym.get("spots_selector"):
                        el = await block.query_selector(gym["spots_selector"])
                        if el:
                            raw = (await el.inner_text()).strip()
                            parsed = parse_spots(raw)
                            if parsed is not None:
                                s["spots_left"] = parsed
                                s["is_full"] = parsed == 0

                    # Fallback: check for full/complet class on the block itself
                    if s["spots_left"] is None and gym.get("full_class"):
                        has_full_class = await block.evaluate(
                            f"el => el.classList.contains('{gym['full_class']}')"
                        )
                        if has_full_class:
                            s["spots_left"] = 0
                            s["is_full"] = True

                    s["session_id"] = make_session_id(s["title"], s["starts_at"], s["coach"])

                    # location_filter: only keep sessions matching this string
                    loc_filter = gym.get("location_filter")
                    if loc_filter:
                        # Check if any text in the block contains the location filter
                        block_text = await block.inner_text()
                        if loc_filter.lower() not in block_text.lower():
                            continue

                    if s["title"] or s["starts_at"]:  # skip empty blocks
                        sessions.append(s)
                except Exception as e:
                    log.error(f"[{gym['id']}] Block parse error: {e}")

        except Exception as e:
            log.error(f"[{gym['id']}] Page load error: {e}")
        finally:
            await browser.close()

    return sessions

def scrape_all_gyms():
    """Run async scraping for all gyms synchronously."""
    async def _run():
        results = {}
        for gym in GYMS:
            if gym.get("disabled"):
                log.info(f"[{gym['id']}] Skipped (disabled)")
                results[gym["id"]] = []
                continue
            sessions = await scrape_gym_playwright(gym)
            results[gym["id"]] = sessions
        return results
    return asyncio.run(_run())

# ── Persistence ───────────────────────────────────────────────────────────────
def upsert_session(con, gym_id, s):
    con.execute("""
        INSERT INTO sessions (gym_id, session_id, coach, title, starts_at, capacity)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(gym_id, session_id) DO UPDATE SET
        coach=excluded.coach, title=excluded.title,
        starts_at=excluded.starts_at, capacity=excluded.capacity
    """, (gym_id, s["session_id"], s["coach"], s["title"], s["starts_at"], s["capacity"]))

def save_snapshot(con, gym_id, s):
    con.execute(
        "INSERT INTO snapshots (gym_id, session_id, captured_at, spots_left, is_full) VALUES (?,?,?,?,?)",
        (gym_id, s["session_id"], datetime.utcnow().isoformat(), s["spots_left"], int(s["is_full"]))
    )

# ── Prediction ────────────────────────────────────────────────────────────────
def predict_full_in_48h(con, gym_id, session_id, capacity) -> bool:
    rows = con.execute(
        "SELECT captured_at, spots_left FROM snapshots WHERE gym_id=? AND session_id=? AND spots_left IS NOT NULL ORDER BY captured_at DESC LIMIT 50",
        (gym_id, session_id)
    ).fetchall()
    if len(rows) < 5: return False
    now = datetime.utcnow()
    times, spots = [], []
    for r in rows:
        try:
            t = datetime.fromisoformat(r["captured_at"])
            times.append((now - t).total_seconds() / 3600)
            spots.append(r["spots_left"])
        except: continue
    if len(times) < 5: return False
    try:
        slope, intercept = np.polyfit(np.array(times), np.array(spots), 1)
        if slope <= 0: return False
        return 0 < (intercept / slope) <= 48
    except: return False

# ── Alerts ────────────────────────────────────────────────────────────────────
def already_alerted(con, gym_id, session_id, alert_type, within_hours=24) -> bool:
    cutoff = (datetime.utcnow() - timedelta(hours=within_hours)).isoformat()
    return con.execute(
        "SELECT id FROM alerts_sent WHERE gym_id=? AND session_id=? AND alert_type=? AND sent_at>?",
        (gym_id, session_id, alert_type, cutoff)
    ).fetchone() is not None

def record_alert(con, gym_id, session_id, alert_type):
    con.execute(
        "INSERT INTO alerts_sent (gym_id, session_id, alert_type, sent_at) VALUES (?,?,?,?)",
        (gym_id, session_id, alert_type, datetime.utcnow().isoformat())
    )

def send_email(subject, body_html):
    cfg = EMAIL_CONFIG
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject; msg["From"] = cfg["from"]; msg["To"] = cfg["to"]
    msg.attach(MIMEText(body_html, "html"))
    try:
        with smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"]) as srv:
            srv.login(cfg["smtp_user"], cfg["smtp_password"])
            srv.sendmail(cfg["from"], cfg["to"], msg.as_string())
        log.info(f"✉️  Email sent: {subject}")
    except Exception as e:
        log.error(f"Email failed: {e}")

def format_alert_email(gym_name, session, alert_type):
    t = session.get("title", "Séance")
    c = session.get("coach", "—")
    h = session.get("starts_at", "—")
    sp = session.get("spots_left")
    if alert_type == "spots_low":
        subj = f"🚨 Plus que {sp} place(s) — {t} ({gym_name})"
        body = f"""<div style="font-family:system-ui;max-width:500px;margin:auto">
          <h2 style="color:#e74c3c">⚠️ Séance bientôt complète !</h2>
          <p><strong>Salle :</strong> {gym_name} &nbsp;|&nbsp; <strong>Séance :</strong> {t}</p>
          <p><strong>Coach :</strong> {c} &nbsp;|&nbsp; <strong>Horaire :</strong> {h}</p>
          <p style="font-size:1.3em;color:#e74c3c"><strong>Places restantes : {sp}</strong></p>
          <p>👉 Réserve ta place maintenant !</p></div>"""
    else:
        subj = f"📈 Séance prédite complète dans 48h — {t} ({gym_name})"
        body = f"""<div style="font-family:system-ui;max-width:500px;margin:auto">
          <h2 style="color:#e67e22">📊 Prédiction : séance complète bientôt</h2>
          <p><strong>Salle :</strong> {gym_name} &nbsp;|&nbsp; <strong>Séance :</strong> {t}</p>
          <p><strong>Coach :</strong> {c} &nbsp;|&nbsp; <strong>Horaire :</strong> {h}</p>
          <p>D'après l'historique, cette séance sera <strong>complète dans &lt;48h</strong>. Réserve maintenant !</p></div>"""
    return subj, body

# ── Main scrape job ───────────────────────────────────────────────────────────
def run_scrape():
    log.info("=== Scrape start ===")
    con = get_db()
    all_sessions = scrape_all_gyms()

    for gym in GYMS:
        sessions = all_sessions.get(gym["id"], [])
        for s in sessions:
            upsert_session(con, gym["id"], s)
            save_snapshot(con, gym["id"], s)
            con.commit()

            sl = s.get("spots_left")
            sid = s["session_id"]
            cap = s.get("capacity") or gym.get("default_capacity")

            if sl is not None and sl <= ALERT_CONFIG["spots_threshold"]:
                if not already_alerted(con, gym["id"], sid, "spots_low"):
                    send_email(*format_alert_email(gym["name"], s, "spots_low"))
                    record_alert(con, gym["id"], sid, "spots_low"); con.commit()
            elif predict_full_in_48h(con, gym["id"], sid, cap):
                if not already_alerted(con, gym["id"], sid, "predicted_full"):
                    send_email(*format_alert_email(gym["name"], s, "predicted_full"))
                    record_alert(con, gym["id"], sid, "predicted_full"); con.commit()

    con.close()
    log.info("=== Scrape done ===")

# ── Flask dashboard ───────────────────────────────────────────────────────────
app = Flask(__name__)

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Gym Tracker</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,sans-serif;background:#f0f2f5;margin:0;padding:24px}
h1{color:#1a1a2e;margin-bottom:4px}.sub{color:#888;font-size:.88em;margin-bottom:28px}
.gym{background:white;border-radius:14px;padding:24px;margin-bottom:24px;box-shadow:0 2px 12px rgba(0,0,0,.07)}
.gym-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}
.gym h2{margin:0;color:#16213e}.gym-url{font-size:.78em;color:#aaa}
.disabled-badge{background:#f0f0f0;color:#999;padding:2px 10px;border-radius:99px;font-size:.8em}
table{width:100%;border-collapse:collapse;font-size:.9em}
th{background:#1a1a2e;color:white;padding:10px 14px;text-align:left;font-weight:500}
td{padding:10px 14px;border-bottom:1px solid #f0f0f0}tr:last-child td{border-bottom:none}
tr.pred{background:#fffbf0}
.badge{display:inline-block;padding:2px 10px;border-radius:99px;font-size:.82em;font-weight:600}
.br{background:#fdecea;color:#c0392b}.bo{background:#fef3e2;color:#d35400}
.bg{background:#eafaf1;color:#1e8449}.bx{background:#f0f0f0;color:#888}
.sf{color:#e74c3c;font-weight:600}.so{color:#e67e22;font-weight:600}.sk{color:#27ae60}
.upd{font-size:.78em;color:#aaa;margin-top:14px}
.btn{display:inline-block;padding:7px 16px;background:#1a1a2e;color:white;border-radius:8px;text-decoration:none;font-size:.85em}
.warning{background:#fff8e1;border-left:4px solid #f59e0b;padding:12px 16px;border-radius:0 8px 8px 0;font-size:.88em;color:#92400e;margin-top:8px}
</style></head><body>
<h1>🏋️ Gym Session Tracker</h1>
<p class="sub">Mise à jour auto toutes les heures &nbsp;·&nbsp; <a href="/scrape-now" class="btn">🔄 Actualiser</a></p>
{% for gym in gyms %}
<div class="gym">
  <div class="gym-header">
    <h2>🏢 {{ gym.name }} {% if gym.disabled %}<span class="disabled-badge">Désactivée</span>{% endif %}</h2>
  </div>
  {% if gym.warning %}<div class="warning">⚠️ {{ gym.warning }}</div>{% endif %}
  {% if gym.sessions and not gym.disabled %}
  <table>
    <tr><th>Séance</th><th>Coach</th><th>Horaire</th><th>Places</th><th>Statut</th></tr>
    {% for s in gym.sessions %}
    <tr class="{{ 'pred' if s.predicted else '' }}">
      <td>{{ s.title or '—' }}</td><td>{{ s.coach or '—' }}</td><td>{{ s.starts_at or '—' }}</td>
      <td>
        {% if s.spots_left is none %}<span class="badge bx">N/A</span>
        {% elif s.spots_left == 0 %}<span class="badge br">Complet</span>
        {% elif s.spots_left <= 2 %}<span class="badge bo">{{ s.spots_left }} place(s)</span>
        {% else %}<span class="badge bg">{{ s.spots_left }}</span>{% endif %}
      </td>
      <td>
        {% if s.is_full %}<span class="sf">🔴 Complet</span>
        {% elif s.spots_left is not none and s.spots_left <= 2 %}<span class="so">🟠 Presque complet</span>
        {% elif s.predicted %}<span class="so">📈 Complet prédit &lt;48h</span>
        {% else %}<span class="sk">🟢 Disponible</span>{% endif %}
      </td>
    </tr>
    {% endfor %}
  </table>
  <p class="upd">Dernière MAJ : {{ gym.updated }}</p>
  {% elif not gym.disabled %}
  <p style="color:#999;font-style:italic">Aucune séance trouvée — le scraping est peut-être en cours ou les sélecteurs doivent être ajustés.</p>
  {% endif %}
</div>
{% endfor %}
</body></html>"""

@app.route("/")
def dashboard():
    con = get_db()
    result = []
    gym_map = {g["id"]: g for g in GYMS}
    for gym in GYMS:
        rows = con.execute("""
            SELECT s.session_id, s.title, s.coach, s.starts_at, s.capacity,
                   sn.spots_left, sn.is_full, sn.captured_at
            FROM sessions s
            LEFT JOIN snapshots sn ON sn.gym_id=s.gym_id AND sn.session_id=s.session_id
              AND sn.id=(SELECT id FROM snapshots WHERE gym_id=s.gym_id AND session_id=s.session_id ORDER BY captured_at DESC LIMIT 1)
            WHERE s.gym_id=? ORDER BY s.starts_at
        """, (gym["id"],)).fetchall()
        sessions = []
        for r in rows:
            sessions.append({
                "title": r["title"], "coach": r["coach"], "starts_at": r["starts_at"],
                "spots_left": r["spots_left"], "is_full": bool(r["is_full"]),
                "predicted": predict_full_in_48h(con, gym["id"], r["session_id"], r["capacity"]),
                "updated": r["captured_at"] or "—"
            })
        result.append({
            "name": gym["name"],
            "sessions": sessions,
            "updated": sessions[0]["updated"] if sessions else "—",
            "disabled": gym.get("disabled", False),
            "warning": gym.get("warning", ""),
        })
    con.close()
    return render_template_string(DASHBOARD_HTML, gyms=result)

@app.route("/api/status")
def api_status():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat(), "gyms": len(GYMS)})

@app.route("/scrape-now")
def scrape_now():
    run_scrape()
    return "<p>✅ Scrape terminé. <a href='/'>← Dashboard</a></p>"

@app.route("/debug/<gym_id>")
def debug_gym(gym_id):
    """Render the gym page with Playwright and return the HTML source + selector matches."""
    gym = next((g for g in GYMS if g["id"] == gym_id), None)
    if not gym:
        return f"<p>Gym '{gym_id}' not found. Available: {[g['id'] for g in GYMS]}</p>", 404

    async def _fetch():
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36"
            )
            await page.goto(gym["url"], wait_until="networkidle", timeout=45000)
            extra_wait = gym.get("extra_wait_ms", 3000)
            await page.wait_for_timeout(extra_wait)
            html = await page.content()
            # Count matches for the session_selector
            sel = gym.get("session_selector", "")
            count = await page.evaluate(f"() => document.querySelectorAll(`{sel}`).length")
            # Get first 3 blocks' outerHTML for inspection
            blocks_html = await page.evaluate(f"""() => {{
                const els = document.querySelectorAll(`{sel}`);
                return Array.from(els).slice(0, 3).map(e => e.outerHTML);
            }}""")
            await browser.close()
            return html, count, blocks_html

    try:
        html, count, blocks_html = asyncio.run(_fetch())
    except Exception as e:
        return f"<pre>Error: {e}</pre>", 500

    # Truncate full HTML to 20 000 chars to stay readable
    html_snippet = html[:20000]
    blocks_section = ""
    for i, b in enumerate(blocks_html):
        blocks_section += f"<h3>Block {i+1}</h3><pre style='white-space:pre-wrap;word-break:break-all;background:#f5f5f5;padding:12px'>{b[:3000]}</pre>"

    return f"""<!DOCTYPE html><html><head><meta charset='UTF-8'>
<title>Debug — {gym['name']}</title>
<style>body{{font-family:system-ui;padding:24px;max-width:1100px;margin:auto}}
pre{{background:#f5f5f5;padding:12px;overflow-x:auto;font-size:.8em}}
h2{{color:#1a1a2e}}.ok{{color:green}}.ko{{color:red}}</style></head><body>
<h1>🔍 Debug — {gym['name']}</h1>
<p><a href='/'>← Dashboard</a> &nbsp;|&nbsp; <strong>URL :</strong> {gym['url']}</p>
<p><strong>session_selector :</strong> <code>{gym.get('session_selector','')}</code></p>
<p class='{'ok' if count > 0 else 'ko'}'><strong>Blocs trouvés : {count}</strong></p>
{blocks_section if count > 0 else "<p class='ko'>Aucun bloc — les sélecteurs ne correspondent pas au DOM rendu.</p>"}
<h2>HTML rendu (20 000 premiers caractères)</h2>
<pre>{html_snippet.replace('<','&lt;').replace('>','&gt;')}</pre>
</body></html>"""

# ── Startup ───────────────────────────────────────────────────────────────────
import threading

init_db()

scheduler = BackgroundScheduler()
scheduler.add_job(run_scrape, "interval", hours=1, id="scrape_job")
scheduler.start()

# Run first scrape in background so Gunicorn can start without timing out
threading.Thread(target=run_scrape, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
