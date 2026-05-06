"""
seed_demo.py  —  Full demo data seeder (users + 15 events)
==========================================================
Creates everything needed for a tomorrow demo:
    1 SuperAdmin  |  1 SPOC  |  5 Judges  |  3 Coordinators  |  20 Students
    15 events across Technical, Cultural, Sports, Management

Run locally (requires Firebase creds):

    # Option A — place the Firebase service account JSON at:
    #   ./serviceAccountKey.json
    # Option B — export FIREBASE_CREDENTIALS='{...full json...}'

    python seed_demo.py
"""
import os, sys, json, datetime


def init_firebase():
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        raw = os.environ.get('FIREBASE_CREDENTIALS')
        if raw:
            cred = credentials.Certificate(json.loads(raw))
        else:
            key = 'serviceAccountKey.json'
            if not os.path.exists(key):
                print("ERROR: set FIREBASE_CREDENTIALS env var or place serviceAccountKey.json in cwd.")
                sys.exit(1)
            cred = credentials.Certificate(key)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def hashpw(raw):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(raw)


# =========================================================
# USERS
# =========================================================
SUPER_ADMIN = {
    "email": "admin@snpsu.edu.in", "name": "System Administrator",
    "role": "SuperAdmin", "category": "All", "phone": "9876500000",
    "password_raw": "Saptha@Admin2026",
}

SPOC = {
    "email": "spoc@snpsu.edu.in", "name": "Priya Sharma",
    "role": "ClubSPOC", "category": "Technical", "phone": "9876500001",
    "password_raw": "Spoc@1234",
}

JUDGES = [
    {"email": f"judge{i}@snpsu.edu.in", "name": n, "role": "Judge",
     "category": c, "phone": f"987650001{i}", "password_raw": f"Judge@{i}{i}{i}{i}"}
    for i, (n, c) in enumerate([
        ("Prof. Arun Menon",   "Technical"),
        ("Dr. Kavitha Rao",    "Cultural"),
        ("Prof. Vinod Shetty", "Sports"),
        ("Dr. Suma Bhat",      "Management"),
        ("Prof. Rajan Pillai", "Technical"),
    ], start=1)
]

COORDINATORS = [
    {"email": f"coord{i}@snpsu.edu.in", "name": n, "role": "EventCoordinator",
     "category": "Technical", "phone": f"987650002{i}", "password_raw": f"Coord@{i}{i}{i}{i}"}
    for i, n in enumerate(["Suresh Babu", "Meena Pillai", "Ramesh Shenoy"], start=1)
]

STUDENTS = [
    {"email": f"student{i:03d}@snpsu.edu.in", "name": n,
     "role": "Student", "category": "General", "phone": f"98765{i:05d}",
     "usn": f"1SNPSU22CS{i:03d}"}
    for i, n in enumerate([
        "Aarav Sharma", "Ananya Rao", "Arjun Pillai", "Divya Nair",
        "Karthik Shetty", "Lavanya Iyer", "Meera Reddy", "Nikhil Kumar",
        "Priya Menon", "Rahul Hegde", "Sahana Kamath", "Sneha Bhat",
        "Tejas Naidu", "Vaishnavi Joshi", "Varun Gowda", "Yamini Murthy",
        "Rohit Patil", "Sanjana Kulkarni", "Mihir Das", "Riya Banerjee"
    ], start=1)
]


# =========================================================
# EVENTS
# =========================================================
# Dates over the next ~3 weeks from today
def _date_offset(days, time_str="10:00 AM"):
    d = datetime.date.today() + datetime.timedelta(days=days)
    return f"{d.strftime('%B %d, %Y')} — {time_str}", d.strftime("%Y-%m-%d"), \
           (d - datetime.timedelta(days=2)).strftime("%Y-%m-%d")


#   (title, category, days_from_today, time, fee, is_team, venue, banner_url)
_U = "https://images.unsplash.com"
EVENTS_SEED = [
    # Technical
    ("HackSaptha 2026",           "Technical",  1,  "9:00 AM", 150, False, "Main Auditorium, Block A",
        f"{_U}/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=1600&q=80"),
    ("CodeRush: DSA Contest",     "Technical",  3,  "2:00 PM", 100, False, "Lab 201, CS Block",
        f"{_U}/photo-1555066931-4365d14bab8c?auto=format&fit=crop&w=1600&q=80"),
    ("AI Innovation Summit",      "Technical",  5, "10:00 AM", 200, True,  "Seminar Hall, Block B",
        f"{_U}/photo-1677442135136-760c813170c8?auto=format&fit=crop&w=1600&q=80"),
    ("Web Dev Championship",      "Technical",  7, "11:00 AM", 120, True,  "Lab 305, IT Block",
        f"{_U}/photo-1461749280684-dccba630e2f6?auto=format&fit=crop&w=1600&q=80"),
    # Cultural
    ("Saptha Voice 2026",         "Cultural",   2,  "6:00 PM",  50, False, "Open Air Theatre",
        f"{_U}/photo-1516280440614-37939bbacd81?auto=format&fit=crop&w=1600&q=80"),
    ("Classical Dance Fiesta",    "Cultural",   4,  "5:00 PM",  80, True,  "Main Auditorium, Block A",
        f"{_U}/photo-1504609813442-a8924e83f76e?auto=format&fit=crop&w=1600&q=80"),
    ("Drama Nite: Ek Kahaani",    "Cultural",   6,  "7:00 PM", 100, True,  "Open Air Theatre",
        f"{_U}/photo-1507924538820-ede94a04019d?auto=format&fit=crop&w=1600&q=80"),
    ("Battle of Bands",           "Cultural",   8,  "6:30 PM", 150, True,  "Amphitheatre",
        f"{_U}/photo-1501612780327-45045538702b?auto=format&fit=crop&w=1600&q=80"),
    # Sports
    ("Inter-Dept Cricket Cup",    "Sports",     9,  "9:00 AM",   0, True,  "Sports Ground",
        f"{_U}/photo-1540747913346-19e32dc3e97e?auto=format&fit=crop&w=1600&q=80"),
    ("Basketball Showdown",       "Sports",    10,  "4:00 PM",   0, True,  "Basketball Court",
        f"{_U}/photo-1546519638-68e109498ffc?auto=format&fit=crop&w=1600&q=80"),
    ("Chess Grand Prix",          "Sports",    11, "10:00 AM",  50, False, "Activity Hall",
        f"{_U}/photo-1528819622765-d6bcf132f793?auto=format&fit=crop&w=1600&q=80"),
    ("Athletics Meet 2026",       "Sports",    12,  "7:00 AM",  30, False, "Athletics Track",
        f"{_U}/photo-1552674605-db6ffd4facb5?auto=format&fit=crop&w=1600&q=80"),
    # Management
    ("B-Plan Pitch Fest",         "Management",13, "10:00 AM", 100, True,  "Conference Hall",
        f"{_U}/photo-1559526324-4b87b5e36e44?auto=format&fit=crop&w=1600&q=80"),
    ("Case Study Crunch",         "Management",14,  "2:00 PM",  80, True,  "Seminar Hall, Block C",
        f"{_U}/photo-1552664730-d307ca884978?auto=format&fit=crop&w=1600&q=80"),
    ("Marketing Mania",           "Management",15, "11:00 AM",  80, False, "Seminar Hall, Block B",
        f"{_U}/photo-1460925895917-afdab827c52f?auto=format&fit=crop&w=1600&q=80"),
]


def build_event(title, category, days_from_now, time_str, fee, team, venue, banner_url,
                spoc_email, spoc_name):
    date_str, date_iso, deadline = _date_offset(days_from_now, time_str)
    return {
        "title": title,
        "category": category,
        "date": date_iso,                 # used by home page filter
        "date_display": date_str,
        "deadline": deadline,
        "venue": venue,
        "overview": f"{title} is a flagship {category.lower()} event at SNPSU. "
                    f"Participants will compete for prizes, certificates, and campus recognition.",
        "description": f"{title} — a {category.lower()} event open to all SNPSU students.",
        "rules": "- Participation open to all SNPSU students\n"
                 "- Follow event-specific guidelines provided on registration\n"
                 "- Unfair practices will lead to disqualification\n"
                 "- Decision of judges is final",
        "prizes": "1st Place: Rs. 10,000 + Trophy + Certificate\n"
                  "2nd Place: Rs. 6,000 + Trophy + Certificate\n"
                  "3rd Place: Rs. 3,000 + Certificate\n"
                  "All participants: Certificate of Participation",
        "judging_criteria": ["Skill", "Creativity", "Execution", "Presentation"],
        "entry_fee":        fee,
        "is_team_event":    team,
        "open_hall_mode":   not team,
        "cert_template":    2,
        "status":           "active",
        "active_round":     1,
        "registration_count": 0,
        "banner_url":       banner_url,
        "media_urls":       [banner_url] if banner_url else [],
        "staff": [{"name": j["name"], "email": j["email"], "role": "Judge"} for j in JUDGES]
               + [{"name": c["name"], "email": c["email"], "role": "EventCoordinator"} for c in COORDINATORS],
        "spoc_id":          spoc_email,
        "created_by":       spoc_name,
        "created_by_email": spoc_email,
        "created_at":       datetime.datetime.now(datetime.timezone.utc),
    }


# =========================================================
# MAIN
# =========================================================
def main():
    print("\n" + "=" * 60)
    print("  SapthaEvent Demo Seeder — Users + 15 Events")
    print("=" * 60)

    db = init_firebase()
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    # --- 1. Users ---------------------------------------------------
    print("\n[1/3] Creating users...")
    all_staff = [SUPER_ADMIN, SPOC] + JUDGES + COORDINATORS
    for u in all_staff:
        db.collection('users').document(u['email']).set({
            'email':               u['email'],
            'name':                u['name'],
            'role':                u['role'],
            'category':            u['category'],
            'phone':               u['phone'],
            'usn':                 u.get('usn', ''),
            'password':            hashpw(u['password_raw']),
            'needs_password_reset': False,
            'is_active':           True,
            'created_at':          today,
        })
        print(f"  OK  [{u['role']:<18s}]  {u['email']:<38s}  pw: {u['password_raw']}")

    for s in STUDENTS:
        db.collection('users').document(s['email']).set({
            'email':               s['email'],
            'name':                s['name'],
            'role':                'Student',
            'category':            'General',
            'phone':               s['phone'],
            'usn':                 s['usn'],
            'password':            hashpw('Student@1234'),
            'needs_password_reset': False,
            'is_active':           True,
            'created_at':          today,
        })
    print(f"  OK  [Student           ]  student001–{len(STUDENTS):03d}@snpsu.edu.in  pw: Student@1234")

    # --- 2. Events --------------------------------------------------
    print(f"\n[2/3] Creating {len(EVENTS_SEED)} events...")
    event_ids = []
    for (title, cat, days, time_str, fee, team, venue, banner) in EVENTS_SEED:
        ev = build_event(title, cat, days, time_str, fee, team, venue, banner,
                         SPOC['email'], SPOC['name'])
        _, ref = db.collection('events').add(ev)
        event_ids.append((title, cat, ref.id, ev['date']))
        print(f"  OK  [{cat:<10s}]  {title:<32s}  {ev['date']}   id={ref.id}")

    # --- 3. Summary -------------------------------------------------
    print(f"\n[3/3] Summary\n" + "-" * 60)
    print(f"  URL: https://saptha-event-portal-production.up.railway.app/login\n")
    print(f"  SUPER ADMIN")
    print(f"    Email:      {SUPER_ADMIN['email']}")
    print(f"    Password:   {SUPER_ADMIN['password_raw']}")
    print(f"    Master Key: <your MASTER_SECRET_KEY in Railway>")
    print(f"\n  SPOC")
    print(f"    {SPOC['email']:<40s} {SPOC['password_raw']}")
    print(f"\n  JUDGES")
    for j in JUDGES:
        print(f"    {j['email']:<40s} {j['password_raw']}")
    print(f"\n  COORDINATORS")
    for c in COORDINATORS:
        print(f"    {c['email']:<40s} {c['password_raw']}")
    print(f"\n  STUDENTS  (all share pw: Student@1234)")
    print(f"    student001@snpsu.edu.in  …  student{len(STUDENTS):03d}@snpsu.edu.in")
    print(f"\n  EVENTS ({len(event_ids)} created)")
    for (t, c, eid, d) in event_ids:
        print(f"    [{c:<10s}]  {d}  {t:<32s}  id={eid}")
    print("-" * 60)


if __name__ == '__main__':
    main()
