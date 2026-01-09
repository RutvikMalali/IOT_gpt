import os
import json
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session
from dotenv import load_dotenv
from openai import OpenAI
from datetime import date, datetime

# ----------------------------
# APP SETUP
# ----------------------------
app = Flask(__name__)
app.secret_key = "iot_gpt_secret"

# ----------------------------
# LOAD API KEY
# ----------------------------
load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
print("API KEY LOADED:", "YES" if API_KEY else "NO")

client = OpenAI(api_key=API_KEY)

# ----------------------------
# DATABASE INIT
# ----------------------------
def init_db():
    conn = sqlite3.connect("iotgpt.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        xp INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 0,
        last_visit TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS chats(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        project TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS domains_used(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        domain TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ----------------------------
# AI FUNCTION — PROJECT DESIGN
# ----------------------------
def get_ai_design(project_idea):

    prompt = f"""
You are an IoT design mentor for beginners.

For the project: "{project_idea}"

Return ONLY valid JSON:

{{
  "introduction": "Brief 2–3 line explanation",
  "microcontroller": "name with short reason",
  "components": ["list of components"],
  "pin_config": ["Component pin → MCU pin"],
  "algorithm": ["step1","step2","step3","step4","step5","step6","step7"],
  "flowchart": "Mermaid flowchart code starting with: flowchart TD",
  "arduino_code": "Complete Arduino sketch using SAME pins"
}}

Rules:
- Arduino code must match pin_config
- Flowchart must be valid Mermaid
- Do NOT add text outside JSON
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    text = response.choices[0].message.content.strip()

    if text.startswith("```"):
        text = text.split("```")[1]

    return json.loads(text)

# ----------------------------
# WOKWI PART MAPPING
# ----------------------------
def component_to_wokwi_part(name):
    n = name.lower()

    if "dht" in n:
        return "wokwi-dht11"
    if "ultrasonic" in n or "hc-sr04" in n:
        return "wokwi-hc-sr04"
    if "lcd" in n:
        return "wokwi-lcd1602"
    if "oled" in n:
        return "wokwi-ssd1306"
    if "relay" in n:
        return "wokwi-relay"
    if "servo" in n:
        return "wokwi-servo"
    if "led" in n:
        return "wokwi-led"
    if "buzzer" in n:
        return "wokwi-buzzer"
    if "gas" in n or "mq" in n:
        return "wokwi-mq2"

    return None

# ----------------------------
# GENERATE WOKWI DIAGRAM JSON
# ----------------------------
def generate_wokwi_diagram(mcu, components):

    if "esp32" in mcu.lower():
        board = "wokwi-esp32-devkit-v1"
    elif "esp8266" in mcu.lower():
        board = "wokwi-esp8266"
    else:
        board = "wokwi-arduino-uno"

    parts = [{
        "id": "mcu",
        "type": board,
        "top": 0,
        "left": 0
    }]

    x = -180
    y = 140
    idx = 0

    for c in components:
        part = component_to_wokwi_part(c)
        if part:
            parts.append({
                "id": f"p{idx}",
                "type": part,
                "top": y,
                "left": x
            })
            idx += 1
            x += 120
            if x > 180:
                x = -180
                y += 120

    diagram = {
        "version": 1,
        "author": "IoT GPT",
        "editor": "wokwi",
        "parts": parts,
        "connections": []
    }

    return json.dumps(diagram, indent=2)

# ----------------------------
# WOKWI SIMULATOR LINK
# ----------------------------
def get_wokwi_link(mcu):

    mcu = mcu.lower()

    if "esp32" in mcu:
        return "https://wokwi.com/projects/new/esp32"
    elif "esp8266" in mcu:
        return "https://wokwi.com/projects/new/esp8266"
    else:
        return "https://wokwi.com/projects/new/arduino-uno"

# ----------------------------
# DOMAIN DETECTION
# ----------------------------
def detect_domains(components):
    domains = set()
    for c in components:
        t = c.lower()
        if any(x in t for x in ["sensor","dht","mq","ultrasonic","ir"]):
            domains.add("sensor")
        if any(x in t for x in ["lcd","oled","display"]):
            domains.add("display")
        if any(x in t for x in ["wifi","cloud","mqtt","thingspeak","esp"]):
            domains.add("cloud")
        if any(x in t for x in ["relay","motor","buzzer","pump","servo"]):
            domains.add("actuator")
    return list(domains)

# ----------------------------
# XP + STREAK
# ----------------------------
def update_xp_and_streak(user_id, domains):
    conn = sqlite3.connect("iotgpt.db")
    c = conn.cursor()

    c.execute("SELECT xp, streak, last_visit FROM users WHERE id=?", (user_id,))
    xp, streak, last_visit = c.fetchone()

    today = date.today().isoformat()

    if last_visit:
        last = datetime.fromisoformat(last_visit).date()
        if (date.today() - last).days == 1:
            streak += 1
        elif (date.today() - last).days > 1:
            streak = 1
    else:
        streak = 1

    gained_xp = 0

    for d in domains:
        c.execute("SELECT 1 FROM domains_used WHERE user_id=? AND domain=?", (user_id,d))
        if c.fetchone():
            gained_xp += 5
        else:
            gained_xp += 30
            c.execute("INSERT INTO domains_used(user_id,domain) VALUES(?,?)",(user_id,d))

    if "cloud" in domains: gained_xp += 30
    if "display" in domains: gained_xp += 20
    if "actuator" in domains: gained_xp += 20

    xp += gained_xp

    c.execute("UPDATE users SET xp=?, streak=?, last_visit=? WHERE id=?",
              (xp, streak, today, user_id))

    conn.commit()
    conn.close()

    return xp, streak, gained_xp

# ----------------------------
# AUTH ROUTES
# ----------------------------
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        u=request.form["username"]
        p=request.form["password"]
        try:
            conn=sqlite3.connect("iotgpt.db")
            c=conn.cursor()
            c.execute("INSERT INTO users(username,password) VALUES(?,?)",(u,p))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))
        except:
            return render_template("signup.html",error="Username exists")
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form["username"]
        p=request.form["password"]
        conn=sqlite3.connect("iotgpt.db")
        c=conn.cursor()
        c.execute("SELECT id FROM users WHERE username=? AND password=?",(u,p))
        user=c.fetchone()
        conn.close()
        if user:
            session["user_id"]=user[0]
            session["username"]=u
            return redirect(url_for("home"))
        else:
            return render_template("login.html",error="Invalid login")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----------------------------
# HOME — PROJECT GENERATOR
# ----------------------------
@app.route("/", methods=["GET","POST"])
def home():

    if "user_id" not in session:
        return redirect(url_for("login"))

    data=None
    gained=None
    sim_link=None
    wokwi_json=None

    conn=sqlite3.connect("iotgpt.db")
    c=conn.cursor()
    c.execute("SELECT id,project FROM chats WHERE user_id=?",(session["user_id"],))
    chats=c.fetchall()
    c.execute("SELECT xp,streak FROM users WHERE id=?",(session["user_id"],))
    xp,streak=c.fetchone()
    conn.close()

    if request.method=="POST":
        project=request.form.get("project")
        try:
            data=get_ai_design(project)

            domains=detect_domains(data["components"])
            xp,streak,gained=update_xp_and_streak(session["user_id"],domains)

            sim_link = get_wokwi_link(data["microcontroller"])
            wokwi_json = generate_wokwi_diagram(
                data["microcontroller"],
                data["components"]
            )

            conn=sqlite3.connect("iotgpt.db")
            c=conn.cursor()
            c.execute("INSERT INTO chats(user_id,project) VALUES(?,?)",(session["user_id"],project))
            conn.commit()
            conn.close()

        except Exception as e:
            print("AI ERROR:",e)

    return render_template(
        "index.html",
        username=session["username"],
        chats=chats,
        xp=xp,
        streak=streak,
        gained=gained,
        sim_link=sim_link,
        wokwi_json=wokwi_json,
        introduction=data["introduction"] if data else None,
        microcontroller=data["microcontroller"] if data else None,
        components=data["components"] if data else None,
        pin_config=data["pin_config"] if data else None,
        algorithm=data["algorithm"] if data else None,
        flowchart=data["flowchart"] if data else None,
        arduino_code=data["arduino_code"] if data else None
    )

# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
