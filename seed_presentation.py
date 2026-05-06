"""
seed_presentation.py
====================
Seeds registrations + pre-loaded judge scores for the HackSaptha 2026 event.

Setup:
  - 6 teams, all marked Present
  - Judge1 & Judge2 have already scored all 6 teams  (pre-loaded)
  - Judge3 has NOT scored yet                        (live demo during presentation)
  - SPOC then publishes results + sends certificates

Run:  python seed_presentation.py
"""

import os, sys, json, datetime, random

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
                print("ERROR: place serviceAccountKey.json in cwd.")
                sys.exit(1)
            cred = credentials.Certificate(key)
        firebase_admin.initialize_app(cred)
    return firestore.client()


# ── Event IDs (from seed_demo.py output) ──────────────────────────────────────
HACKSAPTHA_ID  = "ZAmAxuvOswWwcTz5QUR9"   # HackSaptha 2026  (Technical, team)
CODERUSH_ID    = "en7lCeoUHPqczlcF9UKA"   # CodeRush: DSA    (Technical, individual)

# ── Criteria (must match event doc) ───────────────────────────────────────────
CRITERIA = ["Skill", "Creativity", "Execution", "Presentation"]

# ── Teams for HackSaptha (team event) ─────────────────────────────────────────
#  Each entry: (reg_id, team_name, lead_name, lead_email, member2_name, member2_email)
TEAMS = [
    ("HACK-001", "Team Gamma",  "Karthik Shetty",  "student005@snpsu.edu.in",
                                 "Lavanya Iyer",    "student006@snpsu.edu.in"),
    ("HACK-002", "Team Alpha",  "Aarav Sharma",    "student001@snpsu.edu.in",
                                 "Ananya Rao",      "student002@snpsu.edu.in"),
    ("HACK-003", "Team Echo",   "Priya Menon",     "student009@snpsu.edu.in",
                                 "Rahul Hegde",     "student010@snpsu.edu.in"),
    ("HACK-004", "Team Beta",   "Arjun Pillai",    "student003@snpsu.edu.in",
                                 "Divya Nair",      "student004@snpsu.edu.in"),
    ("HACK-005", "Team Delta",  "Meera Reddy",     "student007@snpsu.edu.in",
                                 "Nikhil Kumar",    "student008@snpsu.edu.in"),
    ("HACK-006", "Team Zeta",   "Sahana Kamath",   "student011@snpsu.edu.in",
                                 "Sneha Bhat",      "student012@snpsu.edu.in"),
]

# ── Individual participants for CodeRush ───────────────────────────────────────
CODERUSH_STUDENTS = [
    ("DSA-001", "Tejas Naidu",     "student013@snpsu.edu.in"),
    ("DSA-002", "Vaishnavi Joshi", "student014@snpsu.edu.in"),
    ("DSA-003", "Varun Gowda",     "student015@snpsu.edu.in"),
    ("DSA-004", "Yamini Murthy",   "student016@snpsu.edu.in"),
    ("DSA-005", "Rohit Patil",     "student017@snpsu.edu.in"),
    ("DSA-006", "Sanjana Kulkarni","student018@snpsu.edu.in"),
    ("DSA-007", "Mihir Das",       "student019@snpsu.edu.in"),
    ("DSA-008", "Riya Banerjee",   "student020@snpsu.edu.in"),
]

# ── Pre-loaded scores (Judge1 & Judge2 already scored, Judge3 scores live) ────
#  Format: { reg_id: { judge_email: [Skill, Creativity, Execution, Presentation] } }
SCORES = {
    "HACK-001": {
        "judge1@snpsu.edu.in": [96, 94, 92, 90],  # avg 93.0
        "judge2@snpsu.edu.in": [94, 92, 94, 92],  # avg 93.0  → combined 93.0  (1st)
    },
    "HACK-002": {
        "judge1@snpsu.edu.in": [92, 88, 90, 86],  # avg 89.0
        "judge2@snpsu.edu.in": [90, 86, 88, 84],  # avg 87.0  → combined 88.0  (2nd)
    },
    "HACK-003": {
        "judge1@snpsu.edu.in": [84, 86, 82, 84],  # avg 84.0
        "judge2@snpsu.edu.in": [86, 84, 80, 82],  # avg 83.0  → combined 83.5  (3rd)
    },
    "HACK-004": {
        "judge1@snpsu.edu.in": [78, 76, 74, 72],  # avg 75.0
        "judge2@snpsu.edu.in": [80, 74, 76, 70],  # avg 75.0  → combined 75.0  (4th)
    },
    "HACK-005": {
        "judge1@snpsu.edu.in": [70, 68, 65, 63],  # avg 66.5
        "judge2@snpsu.edu.in": [68, 70, 64, 62],  # avg 66.0  → combined 66.25 (5th)
    },
    "HACK-006": {
        "judge1@snpsu.edu.in": [58, 62, 60, 56],  # avg 59.0
        "judge2@snpsu.edu.in": [60, 58, 56, 60],  # avg 58.5  → combined 58.75 (6th)
    },
}

# CodeRush individual scores (judge1 already scored, judge2 scores live)
DSA_SCORES = {
    "DSA-001": {"judge1@snpsu.edu.in": [95, 92, 88, 90]},  # avg 91.25
    "DSA-002": {"judge1@snpsu.edu.in": [88, 85, 84, 86]},  # avg 85.75
    "DSA-003": {"judge1@snpsu.edu.in": [76, 78, 74, 72]},  # avg 75.0
    "DSA-004": {"judge1@snpsu.edu.in": [92, 90, 88, 86]},  # avg 89.0
    "DSA-005": {"judge1@snpsu.edu.in": [80, 82, 78, 76]},  # avg 79.0
    "DSA-006": {"judge1@snpsu.edu.in": [70, 68, 72, 66]},  # avg 69.0
    "DSA-007": {"judge1@snpsu.edu.in": [85, 84, 82, 80]},  # avg 82.75
    "DSA-008": {"judge1@snpsu.edu.in": [65, 68, 64, 62]},  # avg 64.75
}


def build_score_entry(values, criteria):
    details = {c: v for c, v in zip(criteria, values)}
    raw     = sum(values)
    avg     = round(raw / len(criteria), 1)
    return {"details": details, "total": avg, "raw_total": raw}


def main():
    print("\n" + "="*60)
    print("  SapthaEvent Presentation Seeder")
    print("="*60)

    db = init_firebase()
    now = datetime.datetime.utcnow().isoformat()

    # ── 1. HackSaptha 2026 — Team Registrations ──────────────────────────────
    print("\n[1/3] Seeding HackSaptha 2026 team registrations...")
    for (reg_id, team, lead_name, lead_email, m2_name, m2_email) in TEAMS:
        raw_scores = SCORES.get(reg_id, {})
        scores_doc = {
            judge: build_score_entry(vals, CRITERIA)
            for judge, vals in raw_scores.items()
        }
        doc = {
            "event_id":      HACKSAPTHA_ID,
            "reg_id":        reg_id,
            "team_name":     team,
            "lead_name":     lead_name,
            "lead_email":    lead_email,
            "members": [
                {"name": lead_name, "email": lead_email},
                {"name": m2_name,   "email": m2_email},
            ],
            "attendance":    "Present",
            "current_round": 1,
            "status":        "registered",
            "payment_status":"paid",
            "scores":        scores_doc,
            "registered_at": now,
        }
        db.collection("registrations").document(reg_id).set(doc)
        judge_count = len(scores_doc)
        if judge_count:
            avg_of_avgs = round(
                sum(s["total"] for s in scores_doc.values()) / judge_count, 1
            )
            print(f"  OK  {reg_id}  {team:<14s}  lead={lead_name:<18s}  "
                  f"judges_scored={judge_count}  current_avg={avg_of_avgs}")
        else:
            print(f"  OK  {reg_id}  {team:<14s}  lead={lead_name:<18s}  (no scores yet)")

    # ── 2. CodeRush: DSA — Individual Registrations ───────────────────────────
    print("\n[2/3] Seeding CodeRush: DSA Contest individual registrations...")
    for (reg_id, name, email) in CODERUSH_STUDENTS:
        raw_scores = DSA_SCORES.get(reg_id, {})
        scores_doc = {
            judge: build_score_entry(vals, CRITERIA)
            for judge, vals in raw_scores.items()
        }
        doc = {
            "event_id":      CODERUSH_ID,
            "reg_id":        reg_id,
            "team_name":     name,
            "lead_name":     name,
            "lead_email":    email,
            "members":       [{"name": name, "email": email}],
            "attendance":    "Present",
            "current_round": 1,
            "status":        "registered",
            "payment_status":"paid",
            "scores":        scores_doc,
            "registered_at": now,
        }
        db.collection("registrations").document(reg_id).set(doc)
        print(f"  OK  {reg_id}  {name:<22s}  email={email}")

    # ── 3. Summary ─────────────────────────────────────────────────────────────
    print(f"\n[3/3] Done!\n" + "-"*60)
    print("  HackSaptha 2026 — Expected leaderboard (after all judges score):")
    expected = [
        ("1st", "Team Gamma",  "Karthik Shetty",  93.0),
        ("2nd", "Team Alpha",  "Aarav Sharma",    88.0),
        ("3rd", "Team Echo",   "Priya Menon",     83.5),
        ("4th", "Team Beta",   "Arjun Pillai",    75.0),
        ("5th", "Team Delta",  "Meera Reddy",     66.25),
        ("6th", "Team Zeta",   "Sahana Kamath",   58.75),
    ]
    for rank, team, lead, avg in expected:
        print(f"  {rank}  {team:<14s}  {lead:<18s}  avg={avg}")
    print("\n  NOTE: Judge3 has NOT scored yet — score live during demo!")
    print("  Judge3 login: judge3@snpsu.edu.in / Judge@3333")
    print("-"*60)


if __name__ == '__main__':
    main()
