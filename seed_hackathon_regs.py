"""
seed_hackathon_regs.py
======================
Seeds 100 students (30 teams, 2-4 members each) into the Hackathon event.
Event ID: 0MlrbbW8TKrc9qpXE2L5  (created by biradark543@gmail.com)

Form field mapping (from event_forms collection):
  full_name  = Lead Full Name   (standard)
  email      = Lead Email       (standard)
  phone      = Lead Phone       (standard)
  f_04wofk   = Lead USN
  f_dm17xb   = Member 1 Name
  f_4hoaqh   = Member 1 Email
  f_urvub0   = Member 1 Phone
  f_omywhv   = Member 1 USN
  f_un0xcw   = Member 2 Name
  f_hf6wus   = Member 2 Email
  f_ff0owl   = Member 2 Phone
  f_ju9kme   = Member 2 USN
  f_t01u4e   = Member 3 Name    (optional)
  f_6cbxu1   = Member 3 Email   (optional)
  f_bmldoa   = Member 3 Phone   (optional)
  f_18vp59   = Member 3 USN     (optional)

Run once:  python3 seed_hackathon_regs.py
"""

import sys
import random
import time
from datetime import datetime, timedelta

sys.path.insert(0, '.')
from models import db

EVENT_ID    = '0MlrbbW8TKrc9qpXE2L5'
EVENT_TITLE = 'Hackathon'

# ── Name pool (Indian names) ─────────────────────────────────────────────────
FIRST = [
    'Aarav','Aditya','Ajay','Akash','Akshay','Anil','Anjali','Ankit','Ankita',
    'Anshul','Anuj','Arjun','Arnav','Aryan','Asha','Ashwin','Ayush','Bhavya',
    'Chetan','Chirag','Deepa','Deepak','Devansh','Dhruv','Disha','Divya',
    'Ganesh','Gaurav','Harini','Harish','Harsh','Hemant','Ishaan','Jaya',
    'Karan','Kartik','Kavya','Komal','Krishna','Kunal','Lakshmi',
    'Mahesh','Manish','Meena','Mihir','Mohan','Mukesh','Nandini','Naveen',
    'Nikhil','Nitin','Omkar','Pooja','Pradeep','Pranav','Prasad','Preethi',
    'Priya','Rahul','Rajesh','Ramesh','Ravi','Ritesh','Rohit','Rupal',
    'Sachin','Sahana','Sai','Sajan','Sandeep','Sanjay','Santosh','Sanya',
    'Shreya','Shubham','Sidharth','Simran','Sneha','Soham','Sumit','Sunil',
    'Suraj','Tanvi','Tejas','Tushar','Uday','Varun','Vikram','Vinay','Vishal',
    'Vivek','Yash','Yogesh','Zoya','Amrita','Bharat','Chandra','Darshan',
    'Esha','Farhan','Geeta','Hema','Imran','Jyothi','Keerthi','Lokesh',
]

LAST = [
    'Acharya','Bhat','Biradar','Chavan','Choudhary','Das','Desai','Deshpande',
    'Garg','Gowda','Gupta','Iyer','Jain','Joshi','Kadam','Kamble','Kapoor',
    'Khanna','Kumar','Malhotra','Mehta','Mishra','Mukherjee','Naik','Nair',
    'Pandey','Patel','Patil','Pillai','Rao','Reddy','Sahoo','Sharma','Shinde',
    'Singh','Sinha','Srivastava','Subramaniam','Swamy','Tiwari','Tripathi',
    'Varma','Verma','Yadav','Banerjee','Chatterjee','Ghosh','Hegde','Kulkarni',
    'Mathur','Nambiar','Oommen','Prasad','Qureshi','Rajan','Saxena','Thomas',
]

BRANCHES = ['BCS', 'ECE', 'BMEC', 'BAIE', 'BCE', 'BITE']
YEAR_BATCHES = {2: '24', 3: '23', 4: '22'}

TEAM_NAMES = [
    'ByteBuilders',       'CodeCrafters',    'HexHawks',       'BinaryBees',
    'PixelPioneers',      'NullPointers',    'StackOverflowers','GitPushers',
    'AlgoAces',           'DataDragons',     'CloudChasers',   'NeuralNinjas',
    'DeepDivers',         'CipherSmiths',    'LambdaLions',    'RuntimeRebels',
    'SyntaxStars',        'KernelKings',     'PacketPirates',  'HashHeroes',
    'ForkForce',          'PullRequestPros', 'MergeMonsters',  'BranchBusters',
    'CommitCrew',         'APIArtisans',     'ServerSorcerers','TokenTigers',
    'QueryQueens',        'RefactorRingers',
]

used_names  = set(['Kiran Biradar'])      # already registered
used_emails = set(['biradark56@gmail.com'])
usn_ctr: dict = {}


def fresh_name():
    for _ in range(200):
        n = random.choice(FIRST) + ' ' + random.choice(LAST)
        if n not in used_names:
            used_names.add(n)
            return n
    # fallback with suffix
    n = random.choice(FIRST) + ' ' + random.choice(LAST) + str(random.randint(2, 9))
    used_names.add(n)
    return n


def fresh_email(name: str) -> str:
    base = name.lower().replace(' ', '.').replace("'", '').replace('0','').replace('1','')
    for tag in [str(random.randint(10, 99)), str(random.randint(100, 999))]:
        e = f'{base}{tag}@gmail.com'
        if e not in used_emails:
            used_emails.add(e)
            return e
    e = f'{base}{random.randint(1000,9999)}@snpsu.edu.in'
    used_emails.add(e)
    return e


def make_usn(year: int) -> str:
    branch = random.choice(BRANCHES)
    key    = (year, branch)
    usn_ctr[key] = usn_ctr.get(key, random.randint(100, 300))
    usn_ctr[key] += 1
    prefix = YEAR_BATCHES[year]
    return f'{prefix}SNPSU{branch}{usn_ctr[key]:04d}'


def rand_phone() -> str:
    return f'+91{random.randint(7000000000, 9999999999)}'


def new_reg_id() -> str:
    ms = int(time.time() * 1000) + random.randint(1, 9999)
    time.sleep(0.001)
    return f'REG-{ms}'


GITHUB_PREFIXES = [
    'team', 'squad', 'bits', 'hack', 'code', 'dev', 'build',
    'make', 'tech', 'gen', 'sol', 'forge', 'byte', 'root',
]


def github_link(slug: str) -> str:
    prefix = random.choice(GITHUB_PREFIXES)
    return f'https://github.com/{prefix}-{slug}/hackathon-2026'


BASE_DT = datetime.now() - timedelta(days=3)


def reg_ts(i: int, total: int) -> str:
    delta = timedelta(seconds=int(3 * 86400 * i / total))
    return (BASE_DT + delta).strftime('%Y-%m-%d %H:%M:%S')


# ── Build teams with sizes that sum to exactly 100 ───────────────────────────
# 20 teams of 3  (= 60)  + 10 teams of 4  (= 40)  = 100 students
SIZES = [3] * 20 + [4] * 10
random.shuffle(SIZES)


def build_teams():
    teams = []
    for i, sz in enumerate(SIZES):
        tname = TEAM_NAMES[i]
        slug  = tname.lower().replace(' ', '-')

        lead_name  = fresh_name()
        lead_year  = random.choice([2, 3, 4])
        lead_email = fresh_email(lead_name)
        lead_phone = rand_phone()
        lead_usn   = make_usn(lead_year)

        members = [{
            'role':  'Lead',
            'name':  lead_name,
            'email': lead_email,
            'phone': lead_phone,
            'usn':   lead_usn,
        }]

        extra = []
        for _ in range(sz - 1):
            mn   = fresh_name()
            myr  = random.choice([2, 3, 4])
            m    = {
                'role':  'Member',
                'name':  mn,
                'email': fresh_email(mn),
                'phone': rand_phone(),
                'usn':   make_usn(myr),
            }
            members.append(m)
            extra.append(m)

        teams.append({
            'team_name':     tname,
            'lead_name':     lead_name,
            'lead_email':    lead_email,
            'lead_phone':    lead_phone,
            'lead_usn':      lead_usn,
            'lead_whatsapp': lead_phone,
            'members':       members,
            'extra':         extra,
            'github_link':   github_link(slug),
        })
    return teams


def form_answers(t: dict) -> dict:
    ex = t['extra']

    def g(j, k):
        if j < len(ex):
            v = ex[j][k]
            return v.replace('+91', '') if k == 'phone' else v
        return ''

    return {
        'full_name': t['lead_name'],
        'email':     t['lead_email'],
        'phone':     t['lead_phone'].replace('+91', ''),
        'f_04wofk':  t['lead_usn'],
        # Member 1
        'f_dm17xb':  g(0, 'name'),
        'f_4hoaqh':  g(0, 'email'),
        'f_urvub0':  g(0, 'phone'),
        'f_omywhv':  g(0, 'usn'),
        # Member 2
        'f_un0xcw':  g(1, 'name'),
        'f_hf6wus':  g(1, 'email'),
        'f_ff0owl':  g(1, 'phone'),
        'f_ju9kme':  g(1, 'usn'),
        # Member 3 (optional)
        'f_t01u4e':  g(2, 'name'),
        'f_6cbxu1':  g(2, 'email'),
        'f_bmldoa':  g(2, 'phone'),
        'f_18vp59':  g(2, 'usn'),
        # Submission
        'github_link': t['github_link'],
    }


def run():
    teams = build_teams()
    total = len(teams)
    student_count = sum(len(t['members']) for t in teams)
    print(f'Seeding {total} teams ({student_count} students) → event "{EVENT_TITLE}" ({EVENT_ID})')

    for i, t in enumerate(teams):
        rid = new_reg_id()
        doc = {
            'reg_id':         rid,
            'event_id':       EVENT_ID,
            'event_title':    EVENT_TITLE,
            'team_name':      t['team_name'],
            'lead_name':      t['lead_name'],
            'lead_email':     t['lead_email'],
            'lead_phone':     t['lead_phone'],
            'lead_usn':       t['lead_usn'],
            'lead_whatsapp':  t['lead_whatsapp'],
            'members':        t['members'],
            'member_count':   len(t['members']),
            'form_type':      'custom',
            'form_answers':   form_answers(t),
            'status':         'Confirmed',
            'payment_status': 'Free',
            'amount_paid':    0,
            'attendance':     'Pending',
            'assigned_room':  '',
            'registered_at':  reg_ts(i, total),
            'current_round':  1,
            'is_eliminated':  False,
        }
        db.collection('registrations').document(rid).set(doc)
        if (i + 1) % 5 == 0:
            print(f'  {i+1:>3}/{total}  {t["team_name"]:<22} ({len(t["members"])} members)')

    # Update event registration_count (30 new + 1 existing)
    db.collection('events').document(EVENT_ID).update({
        'registration_count': total + 1
    })

    print(f'\n✅  {total} teams / {student_count} students added to "{EVENT_TITLE}".')
    print(f'   Event registration_count → {total + 1}')


if __name__ == '__main__':
    run()
