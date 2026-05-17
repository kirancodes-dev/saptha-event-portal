import subprocess
import json
import os

# 10 diverse events to make your app look incredible
events = [
    {"title": "Hack Malenadu '26", "category": "Technical", "venue": "Main Lab", "fee": 0, "minTeamSize": 2, "maxTeamSize": 4, "totalRounds": 2, "date": "2026-06-01"},
    {"title": "RIFT 2026 AI Pitch", "category": "Technical", "venue": "Auditorium", "fee": 150, "minTeamSize": 1, "maxTeamSize": 4, "totalRounds": 3, "date": "2026-06-02"},
    {"title": "Intellimaint Showcase", "category": "Technical", "venue": "Seminar Hall 2", "fee": 50, "minTeamSize": 1, "maxTeamSize": 2, "totalRounds": 1, "date": "2026-06-03"},
    {"title": "Dandeli Trek Expedition", "category": "Sports", "venue": "Main Gate (Bus Pickup)", "fee": 1500, "minTeamSize": 1, "maxTeamSize": 12, "totalRounds": 1, "date": "2026-06-04"},
    {"title": "Box Office Trivia Night", "category": "Cultural", "venue": "Student Lounge", "fee": 20, "minTeamSize": 1, "maxTeamSize": 3, "totalRounds": 3, "date": "2026-06-05"},
    {"title": "Web3 & Smart Contracts", "category": "Technical", "venue": "CS Dept Block", "fee": 100, "minTeamSize": 1, "maxTeamSize": 1, "totalRounds": 1, "date": "2026-06-06"},
    {"title": "Inter-branch Cricket", "category": "Sports", "venue": "University Ground", "fee": 500, "minTeamSize": 11, "maxTeamSize": 15, "totalRounds": 5, "date": "2026-06-07"},
    {"title": "Param Sundari Dance Fest", "category": "Cultural", "venue": "Open Air Theatre", "fee": 200, "minTeamSize": 1, "maxTeamSize": 14, "totalRounds": 2, "date": "2026-06-08"},
    {"title": "FIFA Console Tournament", "category": "Sports", "venue": "Gaming Lab", "fee": 100, "minTeamSize": 1, "maxTeamSize": 1, "totalRounds": 4, "date": "2026-06-09"},
    {"title": "Midnight Coding Challenge", "category": "Technical", "venue": "Library", "fee": 0, "minTeamSize": 1, "maxTeamSize": 2, "totalRounds": 1, "date": "2026-06-10"}
]

print("🚀 Starting the 10-Event Production Database Seed...")

for index, event in enumerate(events):
    # 1. Write the current event to a temporary JSON file
    with open('event_vars_temp.json', 'w') as f:
        json.dump(event, f)
    
    print(f"Injecting [{index + 1}/10]: {event['title']}...")
    
    # 2. Fire the Firebase CLI command securely to the cloud
    subprocess.run([
        "npx", "-y", "firebase-tools@latest", "dataconnect:execute",
        "dataconnect/connector/default/mutations.gql", "CreateEvent",
        "--vars", "@event_vars_temp.json"
    ], stdout=subprocess.DEVNULL) # Hides the massive CLI output for a clean terminal

# 3. Clean up the temp file
if os.path.exists('event_vars_temp.json'):
    os.remove('event_vars_temp.json')

print("✅ Boom! 10 events successfully injected into Aurevix Cloud SQL.")
