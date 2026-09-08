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
    d=request.get_json()
    try:
        age=int(d["age"]); h=float(d["height"]); w=float(d["weight"])
    except Exception: return jsonify(error="Please enter valid age, height and weight."),400
    if not (1<=age<=120 and 50<=h<=250 and 10<=w<=400): return jsonify(error="Please enter realistic values."),400
    lang=d.get("language","en"); problem=(d.get("problem") or "").lower()
    bmi=round(w/(h/100)**2,1)
    c=conn(); rows=c.execute("SELECT * FROM topics").fetchall(); c.close()
    matches=[]
    for r in rows:
        if any(k.lower() in problem for k in json.loads(r["keywords"])):
            matches.append({"name":r["name_hi"] if lang=="hi" else r["name"],"summary":r["summary_hi"] if lang=="hi" else r["summary"],"tips":json.loads(r["tips_hi"] if lang=="hi" else r["tips"]),"help":r["help_hi"] if lang=="hi" else r["help"]})
    if lang=="hi":
        diet=["सब्जियां, फल, दालें और साबुत अनाज जैसे विविध पौष्टिक भोजन शामिल करें।","अत्यधिक मीठे पेय और बहुत अधिक प्रोसेस्ड भोजन सीमित करें।","यदि चिकित्सकीय सलाह न हो तो पर्याप्त पानी पिएं।"]
        habits=["अपनी क्षमता और स्वास्थ्य स्थिति के अनुसार नियमित शारीरिक गतिविधि करें।","नियमित और पर्याप्त नींद लेने की कोशिश करें।","लगातार या बढ़ते लक्षणों पर स्वास्थ्य विशेषज्ञ से सलाह लें।"]
    else:
        diet=["Include vegetables, fruits, pulses/beans and whole grains in a varied eating pattern.","Limit sugary drinks and heavily processed foods.","Drink water regularly unless a clinician advised fluid restriction."]
        habits=["Stay physically active at a level appropriate for your health condition.","Aim for regular and adequate sleep.","Discuss persistent or worsening symptoms with a healthcare professional."]
    urgent=any(x in problem for x in ["chest pain","difficulty breathing","severe bleeding","fainting","सीने में दर्द","सांस लेने में दिक्कत","बेहोशी"])
    return jsonify(bmi=bmi,status=bmi_message(age,bmi,lang),diet=diet,habits=habits,matches=matches,urgent=urgent,urgent_message=("दर्ज किए गए कुछ लक्षणों में तुरंत चिकित्सकीय जांच की आवश्यकता हो सकती है।" if lang=="hi" else "Some entered symptoms may require urgent medical assessment."))

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
