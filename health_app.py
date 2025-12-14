"""
health_app.py
A WxPython healthcare demo app with:
- BMI Calculator
- Book Appointment (SQLite)
- View Appointments
- Symptom Checker (simple rule-based)
- Diet & Activity lookup tab (editable dropdown + export) + integrated Medicine Reminder shortcuts
- Medicine Reminder tab (store reminders & popups)
- Local "AI-like" chatbot for simple queries (availability, appointment questions)

Run:
python health_app.py
"""

import wx
import sqlite3
import datetime
import re
import os
import threading
import time

DB_FILE = "health_app.db"

# ---------- Data: doctors and schedules ----------
DOCTORS = [
    {"id": 1, "name": "Dr. Meera Sharma", "specialty": "Child Specialist", "schedule": [0,1,2,3,4]},  # Mon-Fri
    {"id": 2, "name": "Dr. Ravi Patil",   "specialty": "General Physician", "schedule": [0,1,2,3,4,5]}, # Mon-Sat
    {"id": 3, "name": "Dr. Aisha Khan",   "specialty": "Dermatologist", "schedule": [1,3,5]},         # Tue/Thu/Sat
    {"id": 4, "name": "Dr. Kartik Rao",   "specialty": "Orthopedic", "schedule": [0,2,4]},           # Mon/Wed/Fri
]

# Simple symptom -> conditions rules (very basic illustrative mapping)
SYMPTOM_RULES = {
    "fever": ["Flu", "Viral infection", "COVID-19 (consider testing)"],
    "cough": ["Common cold", "Bronchitis", "COVID-19"],
    "rash": ["Allergic reaction", "Dermatitis", "Chickenpox (if spots)"],
    "stomach": ["Gastritis", "Food poisoning", "Appendicitis (severe, see doc)"],
    "headache": ["Migraine", "Tension headache", "Dehydration"],
    "pain": ["Muscle strain", "Sprain", "Orthopedic issue (if joints)"],
    "sore throat": ["Strep throat", "Common cold"],
    "breath": ["Asthma", "Bronchitis", "Pneumonia (if severe)"],
}

# ---------- Disease guidance (diet & activities) ----------
# NOTE: These are general, illustrative suggestions ONLY.
DISEASE_GUIDANCE = {
    "diabetes": {
        "diet": [
            "Focus on low-GI carbs (whole grains, legumes)",
            "Plenty of non-starchy vegetables",
            "Control portion sizes and eat regularly",
            "Limit sugary drinks and sweets",
            "Prefer lean proteins and healthy fats (nuts, olive oil)"
        ],
        "activities_do": [
            "Moderate aerobic exercise (30 min most days)",
            "Resistance training 2–3 times/week",
            "Daily walks after meals to help blood sugar"
        ],
        "activities_avoid": [
            "Avoid long periods of inactivity",
            "Be cautious with very high-intensity exercise without guidance"
        ]
    },
    "hypertension": {
        "diet": [
            "Reduce salt intake (DASH-style eating)",
            "Increase fruits, vegetables, whole grains",
            "Choose low-fat dairy and lean proteins",
            "Limit processed and high-sodium foods"
        ],
        "activities_do": [
            "Regular aerobic exercise (walking, cycling, swimming)",
            "Stress-reduction activities (yoga, deep breathing)"
        ],
        "activities_avoid": [
            "Avoid heavy alcohol use",
            "Avoid sudden intense exertion if uncontrolled"
        ]
    },
    "obesity": {
        "diet": [
            "Calorie-controlled meals with emphasis on veggies",
            "Reduce sugary drinks and processed snacks",
            "Prioritize protein and fiber to feel full",
            "Use portion control and meal planning"
        ],
        "activities_do": [
            "Start with low-impact cardio (walking, swimming)",
            "Gradually add strength training",
            "Aim for consistent daily activity"
        ],
        "activities_avoid": [
            "Avoid crash diets and extreme calorie restriction",
            "Avoid high-impact workouts until fitness improves"
        ]
    },
    "asthma": {
        "diet": [
            "Maintain a balanced diet and healthy weight",
            "Keep hydrated",
            "If certain foods trigger symptoms, avoid them"
        ],
        "activities_do": [
            "Controlled breathing exercises",
            "Moderate exercise with warm-up (check with doctor)"
        ],
        "activities_avoid": [
            "Avoid exercise in cold, dry air without precautions if it triggers symptoms",
            "Avoid known allergen exposures"
        ]
    },
    "gerd": {
        "diet": [
            "Avoid large meals and lying down after eating",
            "Limit spicy, fatty foods and caffeine",
            "Avoid late-night eating and acidic drinks"
        ],
        "activities_do": [
            "Elevate head of bed if night reflux",
            "Maintain healthy weight"
        ],
        "activities_avoid": [
            "Avoid tight clothing that presses abdomen",
            "Avoid heavy lifting right after meals"
        ]
    },
    "anemia": {
        "diet": [
            "Increase iron-rich foods (leafy greens, legumes, lean red meat if allowed)",
            "Consume vitamin C with iron to improve absorption",
            "Avoid tea/coffee with iron-rich meals"
        ],
        "activities_do": [
            "Gentle exercise (walking), build up as energy improves"
        ],
        "activities_avoid": [
            "Avoid strenuous activity if symptomatic (dizziness, shortness of breath)"
        ]
    },
}

# ---------- DB helpers ----------
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_name TEXT NOT NULL,
            doctor_id INTEGER NOT NULL,
            specialty TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            notes TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            med_name TEXT NOT NULL,
            dose TEXT,
            remind_datetime TEXT NOT NULL,  -- YYYY-MM-DD HH:MM
            notified INTEGER DEFAULT 0,
            note TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_appointment(patient_name, doctor_id, specialty, date_str, time_str, notes=""):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT INTO appointments (patient_name, doctor_id, specialty, date, time, notes) VALUES (?, ?, ?, ?, ?, ?)",
               (patient_name, doctor_id, specialty, date_str, time_str, notes))
    conn.commit()
    conn.close()

def get_appointments():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT id, patient_name, doctor_id, specialty, date, time, notes FROM appointments ORDER BY date, time")
    rows = cur.fetchall()
    conn.close()
    results = []
    for r in rows:
        results.append({
            "id": r[0], "patient_name": r[1], "doctor_id": r[2],
            "specialty": r[3], "date": r[4], "time": r[5], "notes": r[6]
        })
    return results

def delete_appointment(app_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM appointments WHERE id = ?", (app_id,))
    conn.commit()
    conn.close()

# Reminder DB helpers (note: added 'note' column to store free text like diet guidance if needed)
def add_reminder_to_db(med_name, dose, remind_dt_str, note=""):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("INSERT INTO reminders (med_name, dose, remind_datetime, notified, note) VALUES (?, ?, ?, 0, ?)",
               (med_name, dose, remind_dt_str, note))
    conn.commit()
    conn.close()

def get_reminders_from_db(include_notified=True):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    if include_notified:
        cur.execute("SELECT id, med_name, dose, remind_datetime, notified, note FROM reminders ORDER BY remind_datetime")
    else:
        cur.execute("SELECT id, med_name, dose, remind_datetime, notified, note FROM reminders WHERE notified=0 ORDER BY remind_datetime")
    rows = cur.fetchall()
    conn.close()
    return [{"id": r[0], "med_name": r[1], "dose": r[2], "remind_datetime": r[3], "notified": r[4], "note": r[5] } for r in rows]

def delete_reminder_from_db(rem_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("DELETE FROM reminders WHERE id = ?", (rem_id,))
    conn.commit()
    conn.close()

def mark_reminder_notified(rem_id):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET notified = 1 WHERE id = ?", (rem_id,))
    conn.commit()
    conn.close()

# ---------- Utilities ----------
def find_doctor_by_id(did):
    for d in DOCTORS:
        if d["id"] == did:
            return d
    return None

def is_doctor_available_on(doctor, date_obj):
    w = date_obj.weekday()
    return w in doctor["schedule"]

# ---------- Symptom checker ----------
def analyze_symptoms(text):
    text_lower = text.lower()
    found = {}
    for symptom, conds in SYMPTOM_RULES.items():
        if symptom in text_lower:
            for c in conds:
                found[c] = found.get(c, 0) + 1
    if not found:
        return [("No matches found", 0)]
    sorted_found = sorted(found.items(), key=lambda x: -x[1])
    total = sum(found.values())
    result = []
    for cond, score in sorted_found:
        conf = int((score / total) * 100)
        result.append((cond, conf))
    return result

def lookup_disease_guidance(query):
    if not query:
        return None, None
    q = query.strip().lower()
    if q in DISEASE_GUIDANCE:
        return q, DISEASE_GUIDANCE[q]
    for key in DISEASE_GUIDANCE:
        if q in key or key in q:
            return key, DISEASE_GUIDANCE[key]
    q_words = set(re.findall(r"\w+", q))
    best = None
    best_score = 0
    for key in DISEASE_GUIDANCE:
        key_words = set(re.findall(r"\w+", key))
        score = len(q_words & key_words)
        if score > best_score:
            best_score = score
            best = key
    if best_score > 0:
        return best, DISEASE_GUIDANCE[best]
    return None, None

# ---------- Chatbot ----------
def chatbot_reply(message):
    m = message.lower().strip()
    days = {
        "monday":0, "tuesday":1, "wednesday":2, "thursday":3,
        "friday":4, "saturday":5, "sunday":6
    }
    day_found = None
    for name, idx in days.items():
        if name in m:
            day_found = (name, idx)
            break

    specialities = set(d["specialty"].lower() for d in DOCTORS)
    specialty_found = None
    doctor_found = None
    for s in specialities:
        if s in m:
            specialty_found = s
            break
    for d in DOCTORS:
        if d["name"].lower() in m:
            doctor_found = d
            break

    if day_found and (specialty_found or doctor_found):
        day_idx = day_found[1]
        if doctor_found:
            available = day_idx in doctor_found["schedule"]
            if available:
                return f"Yes — {doctor_found['name']} ({doctor_found['specialty']}) is scheduled on {day_found[0].capitalize()}."
            else:
                return f"No — {doctor_found['name']} is not scheduled on {day_found[0].capitalize()}."
        else:
            available_docs = [d for d in DOCTORS if d["specialty"].lower() == specialty_found and day_idx in d["schedule"]]
            if available_docs:
                names = ", ".join(d["name"] for d in available_docs)
                return f"Yes. {names} are scheduled on {day_found[0].capitalize()} for {specialty_found.title()}."
            else:
                return f"No doctors for {specialty_found.title()} are scheduled on {day_found[0].capitalize()}."
    if m.startswith("book") or ("book" in m and "appointment" in m):
        return "I can help book — open the 'Book Appointment' tab and enter patient name, choose doctor or specialty, date and time. I'll save it there."
    if "doctors" in m or "specialist" in m or "specialists" in m:
        lines = []
        for d in DOCTORS:
            days_names = ", ".join(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i] for i in d["schedule"])
            lines.append(f"{d['name']} — {d['specialty']} (Scheduled: {days_names})")
        return "Available doctors:\n" + "\n".join(lines)
    if "hello" in m or "hi" in m:
        return "Hi — I'm the local assistant. Ask me about doctor availability or how to book an appointment."
    return "Sorry, I didn't understand. Try asking: 'Will child specialist be available on Sunday?' or 'How do I book an appointment?'"

# ---------- Reminder background loop ----------
def reminder_check_loop(frame, poll_interval_seconds=30):
    while True:
        try:
            now = datetime.datetime.now()
            rows = get_reminders_from_db(include_notified=False)
            for r in rows:
                try:
                    rem_dt = datetime.datetime.strptime(r["remind_datetime"], "%Y-%m-%d %H:%M")
                except:
                    continue
                if now >= rem_dt:
                    mark_reminder_notified(r["id"])
                    def show_popup(rem=r):
                        wx.MessageBox(f"Medicine reminder:\n{rem['med_name']} — {rem['dose']}\nTime: {rem['remind_datetime']}\n\nNote: {rem.get('note','')}", "Medicine Reminder")
                        try:
                            frame.refresh_reminders_list()
                        except:
                            pass
                    wx.CallAfter(show_popup)
            time.sleep(poll_interval_seconds)
        except Exception:
            time.sleep(poll_interval_seconds)

# ---------- GUI ----------
class HealthApp(wx.Frame):
    def __init__(self):
        super().__init__(parent=None, title="Healthcare Demo App", size=(980,700))
        panel = wx.Panel(self)
        self.notebook = wx.Notebook(panel)

        # tabs
        self.tab_bmi = wx.Panel(self.notebook)
        self.tab_book = wx.Panel(self.notebook)
        self.tab_view = wx.Panel(self.notebook)
        self.tab_symptoms = wx.Panel(self.notebook)
        self.tab_diet = wx.Panel(self.notebook)
        self.tab_reminder = wx.Panel(self.notebook)
        self.tab_chat = wx.Panel(self.notebook)

        self.notebook.AddPage(self.tab_bmi, "BMI Calculator")
        self.notebook.AddPage(self.tab_book, "Book Appointment")
        self.notebook.AddPage(self.tab_view, "View Appointments")
        self.notebook.AddPage(self.tab_symptoms, "Symptom Checker")
        self.notebook.AddPage(self.tab_diet, "Diet & Activity")
        self.notebook.AddPage(self.tab_reminder, "Medicine Reminder")
        self.notebook.AddPage(self.tab_chat, "Assistant (Chatbot)")

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, 6)
        panel.SetSizer(sizer)

        # build tabs
        self.setup_bmi_tab()
        self.setup_book_tab()
        self.setup_view_tab()
        self.setup_symptoms_tab()
        self.setup_diet_tab()        # merged functionality
        self.setup_reminder_tab()
        self.setup_chat_tab()

        self.Centre()
        self.Show()

    # ---- BMI tab ----
    def setup_bmi_tab(self):
        pnl = self.tab_bmi
        box = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(pnl, label="BMI Calculator — enter weight and height")
        box.Add(info, 0, wx.ALL, 6)

        grid = wx.FlexGridSizer(4, 2, 8, 8)
        grid.AddGrowableCol(1)

        grid.Add(wx.StaticText(pnl, label="Weight:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.bmi_weight = wx.TextCtrl(pnl)
        grid.Add(self.bmi_weight, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Height:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.bmi_height = wx.TextCtrl(pnl)
        grid.Add(self.bmi_height, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Units:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.bmi_units = wx.Choice(pnl, choices=["Metric (kg, cm)", "Imperial (lb, in)"])
        self.bmi_units.SetSelection(0)
        grid.Add(self.bmi_units, 1, wx.EXPAND)

        box.Add(grid, 0, wx.ALL|wx.EXPAND, 8)

        self.bmi_result = wx.StaticText(pnl, label="")
        box.Add(self.bmi_result, 0, wx.ALL, 8)

        calc_btn = wx.Button(pnl, label="Calculate BMI")
        calc_btn.Bind(wx.EVT_BUTTON, self.on_calc_bmi)
        box.Add(calc_btn, 0, wx.ALL, 8)

        pnl.SetSizer(box)

    def on_calc_bmi(self, event):
        w = self.bmi_weight.GetValue().strip()
        h = self.bmi_height.GetValue().strip()
        units = self.bmi_units.GetStringSelection()
        try:
            w = float(w)
            h = float(h)
            if "Metric" in units:
                h_m = h / 100.0
                bmi = w / (h_m * h_m)
            else:
                kg = w * 0.45359237
                m = h * 0.0254
                bmi = kg / (m * m)
            bmi = round(bmi, 2)
            if bmi < 18.5:
                cat = "Underweight"
            elif bmi < 25:
                cat = "Normal"
            elif bmi < 30:
                cat = "Overweight"
            else:
                cat = "Obese"
            self.bmi_result.SetLabel(f"BMI = {bmi} ({cat})")
        except Exception:
            self.bmi_result.SetLabel("Enter valid numeric weight and height.")

    # ---- Book tab ----
    def setup_book_tab(self):
        pnl = self.tab_book
        box = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(6, 2, 8, 8)
        grid.AddGrowableCol(1)

        grid.Add(wx.StaticText(pnl, label="Patient name:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.book_name = wx.TextCtrl(pnl)
        grid.Add(self.book_name, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Choose doctor:"), 0, wx.ALIGN_CENTER_VERTICAL)
        doctor_choices = [f"{d['name']} — {d['specialty']}" for d in DOCTORS]
        self.book_doctor = wx.Choice(pnl, choices=doctor_choices)
        self.book_doctor.SetSelection(0)
        grid.Add(self.book_doctor, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Or choose specialty (optional):"), 0, wx.ALIGN_CENTER_VERTICAL)
        specialties = sorted(list({d["specialty"] for d in DOCTORS}))
        self.book_specialty = wx.Choice(pnl, choices=[""] + specialties)
        self.book_specialty.SetSelection(0)
        grid.Add(self.book_specialty, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Date (YYYY-MM-DD):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.book_date = wx.TextCtrl(pnl)
        self.book_date.SetValue(datetime.date.today().isoformat())
        grid.Add(self.book_date, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Time (HH:MM, 24h):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.book_time = wx.TextCtrl(pnl)
        self.book_time.SetValue("10:00")
        grid.Add(self.book_time, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Notes (optional):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.book_notes = wx.TextCtrl(pnl)
        grid.Add(self.book_notes, 1, wx.EXPAND)

        box.Add(grid, 0, wx.ALL | wx.EXPAND, 10)

        btn = wx.Button(pnl, label="Book Appointment")
        btn.Bind(wx.EVT_BUTTON, self.on_book_appointment)
        box.Add(btn, 0, wx.ALL | wx.ALIGN_LEFT, 8)

        self.book_status = wx.StaticText(pnl, label="")
        box.Add(self.book_status, 0, wx.ALL, 6)

        pnl.SetSizer(box)

    def on_book_appointment(self, event):
        name = self.book_name.GetValue().strip()
        doc_idx = self.book_doctor.GetSelection()
        specialty_choice = self.book_specialty.GetStringSelection()
        date_s = self.book_date.GetValue().strip()
        time_s = self.book_time.GetValue().strip()
        notes = self.book_notes.GetValue().strip()
        if not name:
            self.book_status.SetLabel("Patient name is required.")
            return
        try:
            date_obj = datetime.datetime.strptime(date_s, "%Y-%m-%d").date()
            datetime.datetime.strptime(time_s, "%H:%M")
        except Exception:
            self.book_status.SetLabel("Invalid date or time format.")
            return

        doctor = DOCTORS[doc_idx]
        if specialty_choice:
            alt = next((d for d in DOCTORS if d["specialty"] == specialty_choice), None)
            if alt:
                doctor = alt

        if not is_doctor_available_on(doctor, date_obj):
            self.book_status.SetLabel(f"{doctor['name']} is not scheduled on that date.")
            return

        apps = get_appointments()
        for a in apps:
            if a["doctor_id"] == doctor["id"] and a["date"] == date_s and a["time"] == time_s:
                self.book_status.SetLabel("That time is already booked with the selected doctor.")
                return

        add_appointment(name, doctor["id"], doctor["specialty"], date_s, time_s, notes)
        self.book_status.SetLabel("Appointment booked!")
        self.refresh_appointments_list()

    # ---- View tab ----
    def setup_view_tab(self):
        pnl = self.tab_view
        box = wx.BoxSizer(wx.VERTICAL)
        self.apps_list = wx.ListCtrl(pnl, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.apps_list.InsertColumn(0, "ID", width=50)
        self.apps_list.InsertColumn(1, "Patient", width=150)
        self.apps_list.InsertColumn(2, "Doctor", width=200)
        self.apps_list.InsertColumn(3, "Specialty", width=150)
        self.apps_list.InsertColumn(4, "Date", width=90)
        self.apps_list.InsertColumn(5, "Time", width=70)
        self.apps_list.InsertColumn(6, "Notes", width=200)
        box.Add(self.apps_list, 1, wx.ALL | wx.EXPAND, 8)

        btn_box = wx.BoxSizer(wx.HORIZONTAL)
        del_btn = wx.Button(pnl, label="Delete Selected")
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete_selected)
        btn_box.Add(del_btn, 0, wx.ALL, 6)

        refresh_btn = wx.Button(pnl, label="Refresh")
        refresh_btn.Bind(wx.EVT_BUTTON, lambda e: self.refresh_appointments_list())
        btn_box.Add(refresh_btn, 0, wx.ALL, 6)

        box.Add(btn_box, 0, wx.ALIGN_LEFT)
        pnl.SetSizer(box)
        self.refresh_appointments_list()

    def refresh_appointments_list(self):
        self.apps_list.DeleteAllItems()
        apps = get_appointments()
        for a in apps:
            doc = find_doctor_by_id(a["doctor_id"])
            idx = self.apps_list.InsertItem(self.apps_list.GetItemCount(), str(a["id"]))
            self.apps_list.SetItem(idx, 1, a["patient_name"])
            self.apps_list.SetItem(idx, 2, doc["name"] if doc else str(a["doctor_id"]))
            self.apps_list.SetItem(idx, 3, a["specialty"])
            self.apps_list.SetItem(idx, 4, a["date"])
            self.apps_list.SetItem(idx, 5, a["time"])
            self.apps_list.SetItem(idx, 6, a["notes"] or "")

    def on_delete_selected(self, event):
        idx = self.apps_list.GetFirstSelected()
        if idx == -1:
            wx.MessageBox("Select an appointment first.", "Info")
            return
        app_id = int(self.apps_list.GetItemText(idx, 0))
        dlg = wx.MessageDialog(self, "Delete appointment ID %d?" % app_id, "Confirm", wx.YES_NO|wx.NO_DEFAULT)
        if dlg.ShowModal() == wx.ID_YES:
            delete_appointment(app_id)
            self.refresh_appointments_list()

    # ---- Symptom checker tab ----
    def setup_symptoms_tab(self):
        pnl = self.tab_symptoms
        box = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(pnl, label="Type symptoms (e.g. 'fever and cough') and click Analyze")
        box.Add(info, 0, wx.ALL, 8)

        self.symptom_text = wx.TextCtrl(pnl, style=wx.TE_MULTILINE, size=(-1,120))
        box.Add(self.symptom_text, 0, wx.ALL | wx.EXPAND, 8)

        analyze_btn = wx.Button(pnl, label="Analyze")
        analyze_btn.Bind(wx.EVT_BUTTON, self.on_analyze_symptoms)
        box.Add(analyze_btn, 0, wx.ALL, 6)

        self.symptom_results = wx.TextCtrl(pnl, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1,200))
        box.Add(self.symptom_results, 1, wx.ALL | wx.EXPAND, 8)

        pnl.SetSizer(box)

    def on_analyze_symptoms(self, event):
        text = self.symptom_text.GetValue().strip()
        if not text:
            self.symptom_results.SetValue("Please enter symptoms to analyze.")
            return
        results = analyze_symptoms(text)
        lines = []
        for cond, conf in results:
            lines.append(f"{cond} — confidence ~{conf}%")
        lines.append("\nNote: This is a simple symptom checker for demo only. For severe symptoms, see a doctor immediately.")
        self.symptom_results.SetValue("\n".join(lines))

    # ---- Diet & Activity tab (merged) ----
    def setup_diet_tab(self):
        pnl = self.tab_diet
        box = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(pnl, label="Choose or type a disease/disorder name and get general diet & activity suggestions.")
        box.Add(info, 0, wx.ALL, 8)

        # top: combobox + lookup + export + quick-add-reminder
        h = wx.BoxSizer(wx.HORIZONTAL)
        disease_choices = sorted(list(DISEASE_GUIDANCE.keys()))
        self.disease_input = wx.ComboBox(pnl, choices=disease_choices, style=wx.CB_DROPDOWN)
        h.Add(self.disease_input, 1, wx.EXPAND | wx.ALL, 6)

        lookup_btn = wx.Button(pnl, label="Lookup")
        lookup_btn.Bind(wx.EVT_BUTTON, self.on_lookup_disease)
        h.Add(lookup_btn, 0, wx.ALL, 6)

        export_btn = wx.Button(pnl, label="Export")
        export_btn.Bind(wx.EVT_BUTTON, self.on_export_diet)
        h.Add(export_btn, 0, wx.ALL, 6)

        # Quick-add reminder controls (small) on diet tab:
        h.Add(wx.StaticText(pnl, label="  Quick reminder:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        self.quick_med_name = wx.TextCtrl(pnl, size=(160, -1))
        self.quick_med_name.SetHint("Medicine name")
        h.Add(self.quick_med_name, 0, wx.ALL, 6)
        self.quick_dose = wx.TextCtrl(pnl, size=(120, -1))
        self.quick_dose.SetHint("Dose")
        h.Add(self.quick_dose, 0, wx.ALL, 6)
        self.quick_dt = wx.TextCtrl(pnl, size=(150, -1))
        self.quick_dt.SetHint("YYYY-MM-DD HH:MM")
        h.Add(self.quick_dt, 0, wx.ALL, 6)
        add_quick_btn = wx.Button(pnl, label="Add Reminder")
        add_quick_btn.Bind(wx.EVT_BUTTON, self.on_quick_add_reminder)
        h.Add(add_quick_btn, 0, wx.ALL, 6)

        box.Add(h, 0, wx.EXPAND)

        # Results area
        self.disease_results = wx.TextCtrl(pnl, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1,300))
        box.Add(self.disease_results, 1, wx.ALL | wx.EXPAND, 8)

        # Buttons below results
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        copy_to_note_btn = wx.Button(pnl, label="Copy guidance to reminder note")
        copy_to_note_btn.Bind(wx.EVT_BUTTON, self.on_copy_guidance_to_note)
        btn_row.Add(copy_to_note_btn, 0, wx.ALL, 6)

        go_reminder_tab_btn = wx.Button(pnl, label="Open Reminder Tab")
        go_reminder_tab_btn.Bind(wx.EVT_BUTTON, lambda e: self.notebook.SetSelection(self.notebook.GetPageIndex(self.tab_reminder)))
        btn_row.Add(go_reminder_tab_btn, 0, wx.ALL, 6)

        box.Add(btn_row, 0, wx.ALIGN_LEFT)

        warn = wx.StaticText(pnl, label="Warning: suggestions are general examples only. Not a substitute for professional medical advice.")
        warn.SetForegroundColour(wx.Colour(180, 0, 0))
        box.Add(warn, 0, wx.ALL, 6)

        pnl.SetSizer(box)

    def on_lookup_disease(self, event):
        q = self.disease_input.GetValue().strip()
        if not q:
            self.disease_results.SetValue("Please type or choose a disease or disorder name.")
            return
        key, guidance = lookup_disease_guidance(q)
        if guidance is None:
            available = ", ".join(sorted(DISEASE_GUIDANCE.keys()))
            msg = f"No match for '{q}'. Try one of: {available}"
            self.disease_results.SetValue(msg)
            return

        lines = [f"Results for: {key.title()}\n"]
        lines.append("Diet suggestions:")
        for d in guidance.get("diet", []):
            lines.append("- " + d)
        lines.append("\nActivities to DO:")
        for a in guidance.get("activities_do", []):
            lines.append("- " + a)
        lines.append("\nActivities to AVOID:")
        for a in guidance.get("activities_avoid", []):
            lines.append("- " + a)
        lines.append("\nNote: This is general guidance. For personalized advice, consult a healthcare professional.")
        self.disease_results.SetValue("\n".join(lines))

        # Optionally pre-fill quick med name with empty or suggestion (we don't suggest meds)
        # Keep quick fields as-is (user types medicine manually)

    def on_export_diet(self, event):
        content = self.disease_results.GetValue().strip()
        if not content:
            wx.MessageBox("Nothing to export. Lookup suggestions first.", "Info")
            return
        out_dir = "exports"
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(out_dir, f"diet_suggestion_{ts}.txt")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
            wx.MessageBox(f"Exported to {filename}", "Exported")
        except Exception as e:
            wx.MessageBox(f"Failed to export: {e}", "Error")

    def on_quick_add_reminder(self, event):
        med = self.quick_med_name.GetValue().strip()
        dose = self.quick_dose.GetValue().strip()
        dt = self.quick_dt.GetValue().strip()
        note = ""  # optionally you could prefill note from guidance
        if not med or not dt:
            wx.MessageBox("Enter medicine name and date/time (YYYY-MM-DD HH:MM).", "Error")
            return
        try:
            datetime.datetime.strptime(dt, "%Y-%m-%d %H:%M")
        except Exception:
            wx.MessageBox("Date/time must be in format YYYY-MM-DD HH:MM", "Error")
            return
        add_reminder_to_db(med, dose, dt, note)
        wx.MessageBox("Reminder added.", "OK")
        # refresh reminders list in reminder tab (if open)
        try:
            self.refresh_reminders_list()
        except:
            pass

    def on_copy_guidance_to_note(self, event):
        guidance_text = self.disease_results.GetValue().strip()
        if not guidance_text:
            wx.MessageBox("No guidance to copy. Do a lookup first.", "Info")
            return
        # switch to reminder tab & prefill a note area by adding last copied text to quick_med_name's hint (we'll open Reminder tab)
        self.notebook.SetSelection(self.notebook.GetPageIndex(self.tab_reminder))
        # Place the guidance text in the 'note' hint for user convenience (not auto-saving)
        wx.MessageBox("Guidance copied to clipboard-like buffer. In Reminder tab, paste it into the 'Note' field when adding a reminder.", "Copied")
        # actually store it temporarily on the frame for user to paste
        self._last_guidance_text = guidance_text

    # ---- Reminder tab ----
    def setup_reminder_tab(self):
        pnl = self.tab_reminder
        box = wx.BoxSizer(wx.VERTICAL)

        info = wx.StaticText(pnl, label="Add medicine reminders: name, dose, date & time (YYYY-MM-DD HH:MM). You can paste guidance into Note.")
        box.Add(info, 0, wx.ALL, 8)

        grid = wx.FlexGridSizer(4, 2, 8, 8)
        grid.AddGrowableCol(1)

        grid.Add(wx.StaticText(pnl, label="Medicine name:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.rem_med_name = wx.TextCtrl(pnl)
        grid.Add(self.rem_med_name, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Dose (e.g., 1 pill):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.rem_dose = wx.TextCtrl(pnl)
        grid.Add(self.rem_dose, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Date & Time (YYYY-MM-DD HH:MM):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.rem_datetime = wx.TextCtrl(pnl)
        self.rem_datetime.SetValue(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        grid.Add(self.rem_datetime, 1, wx.EXPAND)

        grid.Add(wx.StaticText(pnl, label="Note (optional):"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.rem_note = wx.TextCtrl(pnl)
        grid.Add(self.rem_note, 1, wx.EXPAND)

        box.Add(grid, 0, wx.ALL | wx.EXPAND, 8)

        h = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(pnl, label="Add Reminder")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add_reminder)
        h.Add(add_btn, 0, wx.ALL, 6)
        paste_guidance_btn = wx.Button(pnl, label="Paste Guidance Into Note")
        paste_guidance_btn.Bind(wx.EVT_BUTTON, self.on_paste_guidance_into_note)
        h.Add(paste_guidance_btn, 0, wx.ALL, 6)
        refresh_btn = wx.Button(pnl, label="Refresh List")
        refresh_btn.Bind(wx.EVT_BUTTON, lambda e: self.refresh_reminders_list())
        h.Add(refresh_btn, 0, wx.ALL, 6)
        box.Add(h, 0, wx.ALL, 2)

        self.rem_list = wx.ListCtrl(pnl, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.rem_list.InsertColumn(0, "ID", width=50)
        self.rem_list.InsertColumn(1, "Medicine", width=200)
        self.rem_list.InsertColumn(2, "Dose", width=120)
        self.rem_list.InsertColumn(3, "Remind At", width=160)
        self.rem_list.InsertColumn(4, "Notified", width=80)
        self.rem_list.InsertColumn(5, "Note", width=300)
        box.Add(self.rem_list, 1, wx.ALL | wx.EXPAND, 8)

        del_btn = wx.Button(pnl, label="Delete Selected")
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete_reminder)
        box.Add(del_btn, 0, wx.ALL, 6)

        note = wx.StaticText(pnl, label="Note: App must remain open for reminders to pop up. Times are local and use format YYYY-MM-DD HH:MM.")
        box.Add(note, 0, wx.ALL, 6)

        pnl.SetSizer(box)
        self.refresh_reminders_list()

    def on_add_reminder(self, event):
        name = self.rem_med_name.GetValue().strip()
        dose = self.rem_dose.GetValue().strip()
        dt_str = self.rem_datetime.GetValue().strip()
        note = self.rem_note.GetValue().strip()
        if not name or not dt_str:
            wx.MessageBox("Enter medicine name and date/time.", "Error")
            return
        try:
            datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        except Exception:
            wx.MessageBox("Date/time must be in format YYYY-MM-DD HH:MM", "Error")
            return
        add_reminder_to_db(name, dose, dt_str, note)
        wx.MessageBox("Reminder added.", "OK")
        self.refresh_reminders_list()

    def on_paste_guidance_into_note(self, event):
        guidance = getattr(self, "_last_guidance_text", "")
        if not guidance:
            wx.MessageBox("No copied guidance available. Do a lookup and 'Copy guidance to reminder note' first.", "Info")
            return
        self.rem_note.SetValue(guidance)

    def refresh_reminders_list(self):
        self.rem_list.DeleteAllItems()
        rows = get_reminders_from_db()
        for r in rows:
            idx = self.rem_list.InsertItem(self.rem_list.GetItemCount(), str(r["id"]))
            self.rem_list.SetItem(idx, 1, r["med_name"])
            self.rem_list.SetItem(idx, 2, r["dose"] or "")
            self.rem_list.SetItem(idx, 3, r["remind_datetime"])
            self.rem_list.SetItem(idx, 4, "Yes" if r["notified"] else "No")
            self.rem_list.SetItem(idx, 5, r.get("note","") or "")

    def on_delete_reminder(self, event):
        idx = self.rem_list.GetFirstSelected()
        if idx == -1:
            wx.MessageBox("Select a reminder first.", "Info")
            return
        rem_id = int(self.rem_list.GetItemText(idx, 0))
        dlg = wx.MessageDialog(self, f"Delete reminder ID {rem_id}?", "Confirm", wx.YES_NO|wx.NO_DEFAULT)
        if dlg.ShowModal() == wx.ID_YES:
            delete_reminder_from_db(rem_id)
            self.refresh_reminders_list()

    # ---- Chat tab ----
    def setup_chat_tab(self):
        pnl = self.tab_chat
        box = wx.BoxSizer(wx.VERTICAL)
        self.chat_history = wx.TextCtrl(pnl, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1,350))
        box.Add(self.chat_history, 1, wx.ALL | wx.EXPAND, 8)

        h = wx.BoxSizer(wx.HORIZONTAL)
        self.chat_input = wx.TextCtrl(pnl)
        h.Add(self.chat_input, 1, wx.EXPAND | wx.ALL, 6)
        send_btn = wx.Button(pnl, label="Send")
        send_btn.Bind(wx.EVT_BUTTON, self.on_send_chat)
        h.Add(send_btn, 0, wx.ALL, 6)
        box.Add(h, 0, wx.EXPAND)

        pnl.SetSizer(box)

        welcome = "Assistant ready. You can ask availability e.g. 'Will child specialist be available on Sunday?'\n"
        welcome += "Doctors and schedules:\n"
        for d in DOCTORS:
            schedule_names = ", ".join(["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][i] for i in d["schedule"])
            welcome += f"- {d['name']} ({d['specialty']}): {schedule_names}\n"
        self.chat_history.SetValue(welcome)

    def on_send_chat(self, event):
        msg = self.chat_input.GetValue().strip()
        if not msg:
            return
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        self.chat_history.AppendText(f"\nYou ({now}): {msg}\n")
        reply = chatbot_reply(msg)

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", msg)
        if date_match:
            dstr = date_match.group(1)
            try:
                date_obj = datetime.datetime.strptime(dstr, "%Y-%m-%d").date()
                specialty = None
                for s in set(d["specialty"].lower() for d in DOCTORS):
                    if s in msg.lower():
                        specialty = s
                        break
                if specialty:
                    docs = [d for d in DOCTORS if d["specialty"].lower() == specialty and is_doctor_available_on(d, date_obj)]
                    if docs:
                        reply = f"On {dstr}, the following {specialty.title()} doctors are scheduled: " + ", ".join(d["name"] for d in docs)
                    else:
                        reply = f"No {specialty.title()} doctors scheduled on {dstr}."
            except:
                pass

        self.chat_history.AppendText(f"Assistant: {reply}\n")
        self.chat_input.SetValue("")

import sqlite3
DB_FILE = "health_app.db"
conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()
cur.execute("PRAGMA table_info(reminders)")
cols = [r[1] for r in cur.fetchall()]
if "note" not in cols:
    cur.execute("ALTER TABLE reminders ADD COLUMN note TEXT")
    print("Added note column.")
else:
    print("note column already exists.")
conn.commit()
conn.close()


# ---------- Main ----------
if __name__ == "__main__":
    init_db()
    app = wx.App(False)
    frame = HealthApp()

    # start reminder checker thread (daemon so it exits with app)
    t = threading.Thread(target=reminder_check_loop, args=(frame, 30), daemon=True)
    t.start()

    app.MainLoop()