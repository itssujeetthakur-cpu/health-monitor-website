import os, json, sqlite3
from pathlib import Path
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash

BASE = Path(__file__).parent
DB = BASE / "health.db"
SEED = BASE / "data" / "topics.json"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "development-secret-change-me")
ADMIN_USER = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASSWORD", "change-me-now")

def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    c = conn()
    c.execute("""CREATE TABLE IF NOT EXISTS topics(
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL, name_hi TEXT NOT NULL, keywords TEXT NOT NULL,
        summary TEXT NOT NULL, summary_hi TEXT NOT NULL,
        tips TEXT NOT NULL, tips_hi TEXT NOT NULL,
        help TEXT NOT NULL, help_hi TEXT NOT NULL)""")
    if c.execute("SELECT COUNT(*) FROM topics").fetchone()[0] == 0:
        for t in json.loads(SEED.read_text(encoding="utf-8")):
            c.execute("INSERT INTO topics(name,name_hi,keywords,summary,summary_hi,tips,tips_hi,help,help_hi) VALUES(?,?,?,?,?,?,?,?,?)",
            (t["name"],t["name_hi"],json.dumps(t["keywords"],ensure_ascii=False),t["summary"],t["summary_hi"],json.dumps(t["tips"],ensure_ascii=False),json.dumps(t["tips_hi"],ensure_ascii=False),t["help"],t["help_hi"]))
    c.commit(); c.close()

def admin_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if not session.get("admin"): return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return wrapped

def bmi_message(age, bmi, lang):
    if age < 18:
        return "18 वर्ष से कम उम्र में BMI का मूल्यांकन अलग तरीके से किया जाता है।" if lang=="hi" else "For people under 18, BMI requires age- and sex-specific assessment."
    if bmi < 18.5: return "मानक वयस्क BMI सीमा से कम" if lang=="hi" else "Below the standard adult BMI range"
    if bmi < 25: return "मानक वयस्क BMI सीमा के भीतर" if lang=="hi" else "Within the standard adult BMI range"
    if bmi < 30: return "मानक वयस्क BMI सीमा से ऊपर" if lang=="hi" else "Above the standard adult BMI range"
    return "उच्च BMI सीमा" if lang=="hi" else "High BMI range"

@app.get("/")
def home(): return render_template("index.html")

@app.post("/api/check")
def check():
    d = request.get_json()

    try:
        age = int(d["age"])
        h = float(d["height"])
        w = float(d["weight"])
    except Exception:
        return jsonify(
            error="Please enter valid age, height and weight."
        ), 400

    if not (1 <= age <= 120 and 50 <= h <= 250 and 10 <= w <= 400):
        return jsonify(
            error="Please enter realistic values."
        ), 400

    lang = d.get("language", "en")
    problem = (d.get("problem") or "").lower()
    activity = (d.get("activity") or "low").lower()

    bmi = round(w / (h / 100) ** 2, 1)

    # Find matching health topics from the database
    c = conn()
    rows = c.execute("SELECT * FROM topics").fetchall()
    c.close()

    matches = []

    for r in rows:
        if any(k.lower() in problem for k in json.loads(r["keywords"])):
            matches.append({
                "name": r["name_hi"] if lang == "hi" else r["name"],
                "summary": r["summary_hi"] if lang == "hi" else r["summary"],
                "tips": json.loads(
                    r["tips_hi"] if lang == "hi" else r["tips"]
                ),
                "help": r["help_hi"] if lang == "hi" else r["help"]
            })

    diet = []
    habits = []

    # ---------------- BMI BASED RECOMMENDATIONS ----------------

    if age >= 18:
        if bmi < 18.5:
            diet.extend([
                "Include balanced, nutritious meals regularly.",
                "Include protein-rich foods such as pulses, beans, dairy or other suitable protein sources.",
                "Consider discussing unintentional weight changes with a healthcare professional."
            ])

            habits.extend([
                "Avoid skipping regular meals.",
                "Focus on adequate sleep and recovery."
            ])

        elif bmi < 25:
            diet.extend([
                "Continue eating a varied diet with vegetables, fruits and whole grains.",
                "Include suitable protein sources in your regular meals.",
                "Limit excessive sugary drinks and heavily processed foods."
            ])

            habits.extend([
                "Maintain a regular sleep schedule.",
                "Continue regular physical activity appropriate for your health."
            ])

        elif bmi < 30:
            diet.extend([
                "Focus on vegetables, fruits, pulses and whole grains.",
                "Reduce frequent sugary drinks and heavily processed foods.",
                "Pay attention to regular meal portions."
            ])

            habits.extend([
                "Consider gradually increasing daily physical activity if appropriate.",
                "Avoid sudden or extreme dieting."
            ])

        else:
            diet.extend([
                "Focus on a balanced eating pattern with plenty of nutrient-rich foods.",
                "Limit frequent sugary drinks and heavily processed foods.",
                "Consider professional guidance for personalized nutrition advice."
            ])

            habits.extend([
                "Start physical activity gradually if it is appropriate for you.",
                "Discuss personalized health goals with a qualified healthcare professional."
            ])

    else:
        diet.extend([
            "Focus on a varied and nutritious eating pattern.",
            "Because you are under 18, BMI should be interpreted using age-specific assessment."
        ])

        habits.append(
            "Discuss significant growth, nutrition or weight concerns with a qualified healthcare professional."
        )

    # ---------------- ACTIVITY BASED RECOMMENDATIONS ----------------

    if activity == "low":
        habits.extend([
            "Try adding gentle movement or short walks to your daily routine.",
            "Increase activity gradually according to your comfort and health condition."
        ])

    elif activity == "moderate":
        habits.extend([
            "Maintain regular physical activity and include a mix of movement during the week.",
            "Take regular breaks from long periods of sitting."
        ])

    elif activity == "high":
        diet.extend([
            "Support your activity level with regular balanced meals.",
            "Pay attention to hydration, especially during physical activity."
        ])

        habits.extend([
            "Allow adequate time for rest and recovery.",
            "Avoid pushing through persistent pain or concerning symptoms."
        ])

    # ---------------- SYMPTOM BASED RECOMMENDATIONS ----------------

    if any(word in problem for word in ["headache", "head pain"]):
        habits.append(
            "Pay attention to possible triggers such as inadequate sleep, dehydration or prolonged screen time."
        )

    if any(word in problem for word in ["tired", "fatigue", "weak", "weakness"]):
        diet.append(
            "Make sure your regular meals provide adequate overall nutrition."
        )
        habits.append(
            "Persistent or worsening tiredness should be discussed with a healthcare professional."
        )

    if any(word in problem for word in ["stress", "anxiety", "worried"]):
        habits.extend([
            "Try maintaining a regular sleep routine.",
            "Consider relaxing activities and taking breaks from stressful routines."
        ])

    # Remove duplicate recommendations
    diet = list(dict.fromkeys(diet))
    habits = list(dict.fromkeys(habits))

    urgent_keywords = [
        "chest pain",
        "difficulty breathing",
        "severe bleeding",
        "fainting",
        "सीने में दर्द",
        "सांस लेने में दिक्कत",
        "बेहोशी"
    ]

    urgent = any(x in problem for x in urgent_keywords)

    return jsonify(
        bmi=bmi,
        status=bmi_message(age, bmi, lang),
        activity=activity,
        diet=diet,
        habits=habits,
        matches=matches,
        urgent=urgent,
        urgent_message=(
            "दर्ज किए गए कुछ लक्षणों में तुरंत चिकित्सकीय जांच की आवश्यकता हो सकती है।"
            if lang == "hi"
            else "Some entered symptoms may require urgent medical assessment."
        )
    )
@app.route("/admin/login",methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        if request.form.get("username")==ADMIN_USER and request.form.get("password")==ADMIN_PASS:
            session["admin"]=True; return redirect("/admin")
        flash("Invalid username or password.")
    return render_template("admin_login.html")

@app.get("/admin/logout")
def logout(): session.clear(); return redirect("/admin/login")

@app.get("/admin")
@admin_required
def admin():
    c=conn(); topics=c.execute("SELECT * FROM topics ORDER BY id DESC").fetchall(); c.close()
    return render_template("admin.html",topics=topics)

@app.route("/admin/new",methods=["GET","POST"])
@admin_required
def new():
    if request.method=="POST":
        save_topic(); flash("Topic added."); return redirect("/admin")
    return render_template("topic.html",topic=None)

@app.route("/admin/edit/<int:id>",methods=["GET","POST"])
@admin_required
def edit(id):
    c=conn(); t=c.execute("SELECT * FROM topics WHERE id=?",(id,)).fetchone(); c.close()
    if not t: return "Not found",404
    if request.method=="POST":
        save_topic(id); flash("Topic updated."); return redirect("/admin")
    return render_template("topic.html",topic=t)

@app.post("/admin/delete/<int:id>")
@admin_required
def delete(id):
    c=conn(); c.execute("DELETE FROM topics WHERE id=?",(id,)); c.commit(); c.close()
    flash("Topic deleted."); return redirect("/admin")

def save_topic(id=None):
    f=request.form
    vals=(f["name"],f["name_hi"],json.dumps([x.strip() for x in f["keywords"].split(",") if x.strip()],ensure_ascii=False),f["summary"],f["summary_hi"],json.dumps([x.strip() for x in f["tips"].splitlines() if x.strip()],ensure_ascii=False),json.dumps([x.strip() for x in f["tips_hi"].splitlines() if x.strip()],ensure_ascii=False),f["help"],f["help_hi"])
    c=conn()
    if id: c.execute("UPDATE topics SET name=?,name_hi=?,keywords=?,summary=?,summary_hi=?,tips=?,tips_hi=?,help=?,help_hi=? WHERE id=?",(*vals,id))
    else: c.execute("INSERT INTO topics(name,name_hi,keywords,summary,summary_hi,tips,tips_hi,help,help_hi) VALUES(?,?,?,?,?,?,?,?,?)",vals)
    c.commit(); c.close()

init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=5000,debug=True)
