"""
saptha_full_seed.py  —  SapthaEvent Complete Test Data Seeder
=============================================================
Creates EVERYTHING needed to test the full event lifecycle:

  1 SPOC  |  5 Judges  |  3 Coordinators  |  100 Students
  1 Event (HackSaptha 2026) — fully configured
  100 Registrations — all marked Present, ready for judging

Run order:
  cd C:\\Users\\birad\\sapthagiri_project
  python saptha_full_seed.py

Requirements: firebase_admin, werkzeug  (already in requirements.txt)
"""

import os, sys, json, datetime, time, random

# ── Firebase init ──────────────────────────────────────────────────────
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
                print(f"ERROR: {key} not found and FIREBASE_CREDENTIALS env var not set.")
                sys.exit(1)
            cred = credentials.Certificate(key)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ── Password hashing ───────────────────────────────────────────────────
def hashpw(raw):
    from werkzeug.security import generate_password_hash
    return generate_password_hash(raw)

# ── 100 realistic Indian student names ───────────────────────────────
FIRST_NAMES = [
    "Aarav","Aditya","Akash","Ananya","Anjali","Arjun","Aryan","Ashwin",
    "Bhavana","Deepa","Deepak","Divya","Ganesh","Gautam","Harini","Harish",
    "Ishaan","Jagadish","Karthik","Kavitha","Keerthi","Kiran","Krithika",
    "Lakshmi","Lavanya","Madhav","Mahesh","Manasa","Meena","Mihir",
    "Nandini","Naveen","Neha","Nikhil","Nilufar","Nithin","Pooja","Prabhu",
    "Pradeep","Pranav","Priya","Rahul","Rajeev","Rakesh","Ramya","Ranjith",
    "Rashmi","Ravi","Rohit","Roshan","Sachin","Sahana","Sai","Samanvitha",
    "Sandeep","Sangeetha","Sanjay","Santosh","Saranya","Sathvik","Shashank",
    "Shruti","Sindhu","Sneha","Soumya","Srikanth","Srinivas","Supriya",
    "Suresh","Swathi","Tejas","Tharun","Uday","Vaishnavi","Varun","Vijay",
    "Vikram","Vinay","Vishnu","Yamini","Yashwanth","Zara",
    "Amrutha","Bhuvan","Chandana","Dinesh","Eswar","Faisal","Girish",
    "Hemant","Indira","Jyothi","Kishore","Lokesh","Mithun","Narayan",
    "Omkar","Padma","Qadeer","Rekha","Shilpa","Tanvi"
]

LAST_NAMES = [
    "Sharma","Nair","Reddy","Kumar","Pillai","Shetty","Menon","Rao",
    "Patel","Verma","Singh","Iyer","Krishnan","Hegde","Kamath","Bhat",
    "Naidu","Joshi","Gowda","Murthy","Patil","Kulkarni","Bhatt","Das",
    "Mishra","Tiwari","Pandey","Gupta","Agarwal","Shah","Mehta","Kapoor",
    "Malhotra","Saxena","Srivastava","Dubey","Chaudhary","Banerjee","Ghosh",
    "Biswas","Dey","Chakraborty","Bose","Mukherjee","Roy","Sen","Paul"
]

DEPTS = ["CS","EC","ME","CV","IS","EE"]

def make_students(n=100):
    random.seed(42)
    names_used = set()
    students = []
    fn_list = FIRST_NAMES * 2
    ln_list = LAST_NAMES * 3
    random.shuffle(fn_list)
    random.shuffle(ln_list)
    i = 0
    while len(students) < n:
        fname = fn_list[i % len(fn_list)]
        lname = ln_list[i % len(ln_list)]
        full  = f"{fname} {lname}"
        if full in names_used:
            i += 1
            continue
        names_used.add(full)
        num    = len(students) + 1
        dept   = DEPTS[num % len(DEPTS)]
        year   = random.choice(['21','22','23'])
        email  = f"student{num:03d}@snpsu.edu.in"
        usn    = f"1SNPSU{year}{dept}{num:03d}"
        phone  = f"98765{num:05d}"
        students.append({
            "num":   num,
            "name":  full,
            "email": email,
            "usn":   usn,
            "phone": phone,
            "dept":  dept,
        })
        i += 1
    return students

# ── User definitions ───────────────────────────────────────────────────
SPOC = {
    "email":    "spoc@snpsu.edu.in",
    "name":     "Priya Sharma",
    "role":     "ClubSPOC",
    "category": "Technical",
    "phone":    "9876500001",
    "usn":      "",
    "password_raw": "Spoc@1234",
}

JUDGES = [
    {"email":"judge1@snpsu.edu.in","name":"Prof. Arun Menon",  "role":"Judge","category":"Technical","phone":"9876500010","password_raw":"Judge@1111"},
    {"email":"judge2@snpsu.edu.in","name":"Dr. Kavitha Rao",   "role":"Judge","category":"Technical","phone":"9876500011","password_raw":"Judge@2222"},
    {"email":"judge3@snpsu.edu.in","name":"Prof. Vinod Shetty","role":"Judge","category":"Technical","phone":"9876500012","password_raw":"Judge@3333"},
    {"email":"judge4@snpsu.edu.in","name":"Dr. Suma Bhat",     "role":"Judge","category":"Technical","phone":"9876500013","password_raw":"Judge@4444"},
    {"email":"judge5@snpsu.edu.in","name":"Prof. Rajan Pillai","role":"Judge","category":"Technical","phone":"9876500014","password_raw":"Judge@5555"},
]

COORDINATORS = [
    {"email":"coord1@snpsu.edu.in","name":"Suresh Babu",  "role":"EventCoordinator","category":"Technical","phone":"9876500020","password_raw":"Coord@1111"},
    {"email":"coord2@snpsu.edu.in","name":"Meena Pillai", "role":"EventCoordinator","category":"Technical","phone":"9876500021","password_raw":"Coord@2222"},
    {"email":"coord3@snpsu.edu.in","name":"Ramesh Shenoy","role":"EventCoordinator","category":"Technical","phone":"9876500022","password_raw":"Coord@3333"},
]

# ── Event definition ───────────────────────────────────────────────────
EVENT = {
    "title":    "HackSaptha 2026",
    "category": "Technical",
    "date":     "April 15, 2026 — 9:00 AM",
    "deadline": "2026-04-10",
    "venue":    "Main Auditorium, Block A, SNPSU",
    "overview": (
        "HackSaptha 2026 is SNPSU's flagship individual hackathon where "
        "participants build innovative solutions to real-world problems over 8 hours. "
        "Projects are judged on innovation, technical depth, impact, and final presentation. "
        "Open to all SNPSU students across all departments."
    ),
    "rules": (
        "- Solo participation only\n"
        "- All code must be written during the event\n"
        "- Use of open-source libraries and public APIs is allowed\n"
        "- Submit GitHub repo link before judging begins\n"
        "- Plagiarism leads to immediate disqualification\n"
        "- Participants must be present at venue for the entire duration"
    ),
    "prizes": (
        "1st Place: Rs. 15,000 + Gold Trophy + Certificate of Achievement\n"
        "2nd Place: Rs. 10,000 + Silver Trophy + Certificate of Achievement\n"
        "3rd Place: Rs.  5,000 + Bronze Trophy + Certificate of Achievement\n"
        "All Participants: Certificate of Participation"
    ),
    "judging_criteria": ["Innovation", "Technical Complexity", "Impact", "Presentation"],
    "entry_fee":        100,
    "is_team_event":    False,
    "open_hall_mode":   True,
    "cert_template":    2,
    "status":           "active",
    "active_round":     1,
    "registration_count": 0,
    "banner_url":       "",
    "media_urls":       [],
    "staff": [
        {"name": j["name"], "email": j["email"], "role": "Judge"}
        for j in JUDGES
    ] + [
        {"name": c["name"], "email": c["email"], "role": "EventCoordinator"}
        for c in COORDINATORS
    ],
    "created_by":       SPOC["name"],
    "created_by_email": SPOC["email"],
}

# ── Main seeder ────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  SapthaEvent Full Test Data Seeder")
    print("="*60)

    db = init_firebase()
    now = datetime.datetime.utcnow()
    today = now.strftime("%Y-%m-%d")

    # ── 1. Create / update users ──────────────────────────────────────
    print("\n[1/4] Creating users...")

    all_users = [SPOC] + JUDGES + COORDINATORS
    for u in all_users:
        ref = db.collection('users').document(u['email'])
        ref.set({
            'email':               u['email'],
            'name':                u['name'],
            'role':                u['role'],
            'category':            u['category'],
            'phone':               u['phone'],
            'usn':                 u.get('usn', ''),
            'password':            hashpw(u['password_raw']),
            'needs_password_reset': False,
            'created_at':          today,
        })
        tag = f"[{u['role']:<18s}]"
        print(f"  OK  {tag}  {u['email']:<38s}  pw: {u['password_raw']}")

    students = make_students(100)
    for s in students:
        ref = db.collection('users').document(s['email'])
        ref.set({
            'email':               s['email'],
            'name':                s['name'],
            'role':                'Student',
            'category':            'General',
            'phone':               s['phone'],
            'usn':                 s['usn'],
            'password':            hashpw('Student@1234'),
            'needs_password_reset': False,
            'created_at':          today,
        })
    print(f"  OK  [Student           ]  student001–100@snpsu.edu.in  pw: Student@1234")
    print(f"      Users created: {len(all_users)} staff + 100 students\n")

    # ── 2. Create event ───────────────────────────────────────────────
    print("[2/4] Creating event...")

    ev_data = dict(EVENT)
    ev_data['created_at'] = now
    ev_data['description'] = ev_data['overview'][:120] + '...'

    _, ev_ref = db.collection('events').add(ev_data)
    event_id    = ev_ref.id
    event_title = ev_data['title']
    print(f"  OK  Event ID: {event_id}")
    print(f"      Title:    {event_title}\n")

    # ── 3. Create 100 registrations (all Present) ─────────────────────
    print("[3/4] Creating 100 registrations (all marked Present)...")

    batch_size = 20
    reg_ids    = []
    batch      = db.batch()
    count      = 0

    for s in students:
        reg_id = f"REG-HACK{s['num']:03d}-{int(time.time()*1000) % 100000}"
        reg_ids.append(reg_id)
        reg_ref = db.collection('registrations').document(reg_id)
        batch.set(reg_ref, {
            'reg_id':          reg_id,
            'event_id':        event_id,
            'event_title':     event_title,
            'lead_name':       s['name'],
            'lead_email':      s['email'],
            'lead_usn':        s['usn'],
            'lead_phone':      s['phone'],
            'team_name':       'Individual',
            'members':         [],
            'status':          'Confirmed',
            'payment_status':  'Paid',
            'amount_paid':     ev_data['entry_fee'],
            'registered_at':   now.strftime("%Y-%m-%d %H:%M:%S"),
            'attendance':      'Present',
            'checkin_time':    '09:15:00',
            'is_eliminated':   False,
            'current_round':   1,
            'scores':          {},
            'final_score':     None,
            'final_rank':      None,
        })
        count += 1
        if count % batch_size == 0:
            batch.commit()
            batch = db.batch()
            print(f"  ...{count}/100 registered")
    if count % batch_size != 0:
        batch.commit()

    # Update registration_count on event
    ev_ref.update({'registration_count': 100})
    print(f"  OK  100 registrations created — all marked Present\n")

    # ── 4. Print summary ──────────────────────────────────────────────
    print("[4/4] Done! Full summary:\n")
    print("─"*60)
    print(f"  LOGIN URL   https://saptha-event-portal-production.up.railway.app/login")
    print("─"*60)
    print(f"\n  SPOC")
    print(f"    {SPOC['email']:<40s} {SPOC['password_raw']}")
    print(f"\n  JUDGES  (dashboard: /judge/dashboard)")
    for j in JUDGES:
        print(f"    {j['email']:<40s} {j['password_raw']}")
    print(f"\n  COORDINATORS  (dashboard: /coordinator/scanner)")
    for c in COORDINATORS:
        print(f"    {c['email']:<40s} {c['password_raw']}")
    print(f"\n  STUDENTS  (dashboard: /participant/dashboard)")
    print(f"    student001@snpsu.edu.in  …  student100@snpsu.edu.in")
    print(f"    Password: Student@1234  (same for all)")
    print(f"\n  EVENT")
    print(f"    ID:       {event_id}")
    print(f"    Title:    {event_title}")
    print(f"    Students: 100 registered + Present")
    print(f"    Judges:   5 (Open Hall Mode — all see all students)")
    print(f"    Criteria: Innovation · Technical Complexity · Impact · Presentation")
    print("─"*60)
    print(f"\n  NEXT STEPS:")
    print(f"  1. Log in as judge1–5@snpsu.edu.in and submit scores")
    print(f"  2. Log in as spoc@snpsu.edu.in → View Scores → Publish Results")
    print(f"  3. Check student emails for certificates")
    print("─"*60)
    print()

    # Save event_id to file for reference
    with open('test_event_id.txt', 'w') as f:
        f.write(event_id)
    print(f"  Event ID saved to test_event_id.txt\n")

if __name__ == '__main__':
    main()