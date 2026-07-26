"""
seed_emulator.py — Seed 30 events into the SQL Connect local emulator.
Emulator must be running: firebase emulators:start --only dataconnect
Run: python scripts/seed_emulator.py
"""
import sys
from datetime import date, timedelta

try:
    import requests
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests', '-q'])
    try:
        import requests
    except Exception:
        requests = None

BASE = "http://localhost:9399/v1beta/projects/aurevix/locations/us-east4/services/aurevix-service/connectors/example:executeMutation"
TODAY = date.today()

def d(offset):
    return (TODAY + timedelta(days=offset)).isoformat()

def run(operation, variables):
    resp = requests.post(BASE, json={
        "operationName": operation,
        "variables": variables,
    }, headers={"Content-Type": "application/json"})
    if resp.status_code != 200:
        print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
        return None
    body = resp.json()
    if body.get("errors"):
        print(f"  GQL ERROR: {body['errors'][0].get('message','?')[:120]}")
        return None
    return body.get("data")

events = [
    # Technical (10)
    dict(title="HackFusion 2026",           category="Technical",  date=d(5),  deadline=d(3),  venue="Innovation Lab, Block A",          fee=200,  minTeamSize=2, maxTeamSize=4,  totalRounds=3, prizes="₹50,000 cash + internship"),
    dict(title="CodeSprint Championship",   category="Technical",  date=d(8),  deadline=d(6),  venue="CS Seminar Hall",                  fee=100,  minTeamSize=1, maxTeamSize=1,  totalRounds=2, prizes="₹20,000 + trophy"),
    dict(title="AI/ML Datathon",            category="Technical",  date=d(12), deadline=d(10), venue="Data Science Lab",                 fee=250,  minTeamSize=2, maxTeamSize=3,  totalRounds=2, prizes="₹30,000 + certificates"),
    dict(title="Robo Wars 2026",            category="Technical",  date=d(15), deadline=d(13), venue="Mechanical Workshop Arena",        fee=500,  minTeamSize=2, maxTeamSize=5,  totalRounds=3, prizes="₹40,000 + trophy"),
    dict(title="Web Dev Blitz",             category="Technical",  date=d(18), deadline=d(16), venue="Computer Centre, Floor 2",         fee=150,  minTeamSize=1, maxTeamSize=2,  totalRounds=2, prizes="₹15,000 cash"),
    dict(title="Cybersecurity CTF",         category="Technical",  date=d(22), deadline=d(20), venue="Networking Lab",                   fee=100,  minTeamSize=2, maxTeamSize=4,  totalRounds=2, prizes="₹25,000 + goodies"),
    dict(title="IoT Innovation Challenge",  category="Technical",  date=d(25), deadline=d(23), venue="Electronics Lab",                  fee=300,  minTeamSize=2, maxTeamSize=4,  totalRounds=2, prizes="₹35,000 + internship"),
    dict(title="App Dev Hackathon",         category="Technical",  date=d(30), deadline=d(28), venue="Mobile Lab, Block C",              fee=200,  minTeamSize=2, maxTeamSize=3,  totalRounds=2, prizes="₹20,000 cash"),
    dict(title="Cloud Computing Quiz",      category="Technical",  date=d(33), deadline=d(31), venue="Seminar Hall 1",                   fee=50,   minTeamSize=1, maxTeamSize=1,  totalRounds=1, prizes="₹5,000 + certs"),
    dict(title="Database Design Contest",   category="Technical",  date=d(37), deadline=d(35), venue="CS Lab 3",                         fee=100,  minTeamSize=1, maxTeamSize=2,  totalRounds=2, prizes="₹10,000 cash"),
    # Cultural (8)
    dict(title="Spotlight Solo Singing",    category="Cultural",   date=d(6),  deadline=d(4),  venue="Open Air Auditorium",              fee=0,    minTeamSize=1, maxTeamSize=1,  totalRounds=2, prizes="₹10,000 + trophy"),
    dict(title="Battle of Bands",           category="Cultural",   date=d(9),  deadline=d(7),  venue="Main Auditorium",                  fee=500,  minTeamSize=3, maxTeamSize=8,  totalRounds=2, prizes="₹25,000 + recording deal"),
    dict(title="Nukkad Natak (Street Play)",category="Cultural",   date=d(14), deadline=d(12), venue="Central Plaza",                    fee=200,  minTeamSize=5, maxTeamSize=12, totalRounds=2, prizes="₹15,000 cash"),
    dict(title="Classical Dance Fiesta",    category="Cultural",   date=d(19), deadline=d(17), venue="Main Auditorium",                  fee=100,  minTeamSize=1, maxTeamSize=6,  totalRounds=2, prizes="₹12,000 + trophy"),
    dict(title="Western Dance Crew Battle", category="Cultural",   date=d(24), deadline=d(22), venue="Main Auditorium",                  fee=300,  minTeamSize=4, maxTeamSize=10, totalRounds=2, prizes="₹20,000 cash"),
    dict(title="Photography Hunt",          category="Cultural",   date=d(28), deadline=d(26), venue="SNPSU Campus (All Zones)",         fee=100,  minTeamSize=1, maxTeamSize=1,  totalRounds=1, prizes="₹8,000 + exhibition"),
    dict(title="Short Film Showcase",       category="Cultural",   date=d(35), deadline=d(30), venue="Seminar Hall 2",                   fee=200,  minTeamSize=2, maxTeamSize=6,  totalRounds=1, prizes="₹15,000 + OTT feature"),
    dict(title="Mr & Ms Saptha 2026",       category="Cultural",   date=d(40), deadline=d(35), venue="Main Auditorium",                  fee=0,    minTeamSize=1, maxTeamSize=1,  totalRounds=3, prizes="Crown + ₹20,000"),
    # Sports (7)
    dict(title="Badminton Singles Open",    category="Sports",     date=d(5),  deadline=d(3),  venue="Indoor Sports Complex",            fee=100,  minTeamSize=1, maxTeamSize=1,  totalRounds=4, prizes="₹8,000 + trophy"),
    dict(title="Football 5-a-Side League",  category="Sports",     date=d(10), deadline=d(8),  venue="Football Ground",                  fee=500,  minTeamSize=5, maxTeamSize=5,  totalRounds=3, prizes="₹20,000 + medals"),
    dict(title="Cricket T10 Tournament",    category="Sports",     date=d(15), deadline=d(12), venue="Cricket Ground",                   fee=1000, minTeamSize=11,maxTeamSize=14, totalRounds=3, prizes="₹30,000 + trophy"),
    dict(title="Throwball Championship",    category="Sports",     date=d(20), deadline=d(18), venue="Open Sports Court",                fee=300,  minTeamSize=7, maxTeamSize=9,  totalRounds=3, prizes="₹12,000 + medals"),
    dict(title="Table Tennis Doubles",      category="Sports",     date=d(26), deadline=d(24), venue="Indoor Sports Complex",            fee=150,  minTeamSize=2, maxTeamSize=2,  totalRounds=3, prizes="₹6,000 + trophy"),
    dict(title="Carrom Board Open",         category="Sports",     date=d(31), deadline=d(29), venue="Recreation Centre",                fee=50,   minTeamSize=1, maxTeamSize=2,  totalRounds=3, prizes="₹4,000 cash"),
    dict(title="Tug of War Smackdown",      category="Sports",     date=d(38), deadline=d(36), venue="Sports Ground",                    fee=200,  minTeamSize=8, maxTeamSize=10, totalRounds=2, prizes="₹10,000 + trophy"),
    # Management (5)
    dict(title="Startup Pitch Fest",        category="Management", date=d(7),  deadline=d(5),  venue="Entrepreneurship Cell Auditorium", fee=300,  minTeamSize=2, maxTeamSize=4,  totalRounds=3, prizes="₹50,000 seed funding"),
    dict(title="Business Case Study",       category="Management", date=d(13), deadline=d(11), venue="MBA Block Seminar Hall",           fee=200,  minTeamSize=2, maxTeamSize=4,  totalRounds=2, prizes="₹20,000 + internship"),
    dict(title="Marketing Blitz",           category="Management", date=d(21), deadline=d(19), venue="Conference Room A",                fee=150,  minTeamSize=2, maxTeamSize=3,  totalRounds=2, prizes="₹15,000 cash"),
    dict(title="HR Simulation Challenge",   category="Management", date=d(29), deadline=d(27), venue="Conference Room B",                fee=100,  minTeamSize=2, maxTeamSize=3,  totalRounds=2, prizes="₹10,000 + certs"),
    dict(title="Finance Quiz & Trading Sim",category="Management", date=d(36), deadline=d(34), venue="Commerce Lab",                     fee=100,  minTeamSize=1, maxTeamSize=2,  totalRounds=2, prizes="₹12,000 cash"),
]

print(f"Seeding {len(events)} events into emulator at {BASE}\n")
ok = 0
for i, ev in enumerate(events, 1):
    result = run("CreateEvent", {
        "title":        ev["title"],
        "category":     ev["category"],
        "date":         ev["date"],
        "deadline":     ev["deadline"],
        "venue":        ev["venue"],
        "fee":          float(ev["fee"]),
        "minTeamSize":  ev["minTeamSize"],
        "maxTeamSize":  ev["maxTeamSize"],
        "totalRounds":  ev["totalRounds"],
        "prizes":       ev["prizes"],
        "coordinatorId":"biradark543@gmail.com",
    })
    status = "✓" if result else "✗"
    print(f"  [{i:02d}/30] {status} {ev['category']:<12} {ev['title']}")
    if result:
        ok += 1

print(f"\n{ok}/30 events seeded into emulator.")
if ok < len(events):
    print("Check that: firebase emulators:start --only dataconnect is running.")
