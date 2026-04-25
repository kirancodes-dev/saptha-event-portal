"""
seed_events.py
==============
Creates 3 ClubSPOC users + 30 seeded events + event_forms docs in Firestore.

Registration forms:
  Solo events  → simple form  (Name, Email, Phone, USN, Year, Branch)
  Team events  → team form    (Team Name + Leader details + N member slots)
  Both events  → flex form    (same as team but team_name / members optional)

Run once:  python3 seed_events.py
"""

import datetime
import sys
import os
os.environ.setdefault('FIREBASE_KEY_PATH', 'serviceAccountKey.json')

from models import db
from werkzeug.security import generate_password_hash

# ──────────────────────────────────────────────────────────────
# 3 SPOC ACCOUNTS
# ──────────────────────────────────────────────────────────────
SPOCS = {
    'itc': {
        'email':         'priya.nair@snpsu.ac.in',
        'name':          'Priya Nair',
        'phone':         '+91 98765 43210',
        'club':          'Innovation & Technology Club (ITC)',
        'password':      'SPOC@Priya2026',
        'role':          'ClubSPOC',
        'category':      'Technical',
        'whatsapp_group': 'https://chat.whatsapp.com/snpsu-itc-2026',
    },
    'acs': {
        'email':         'arjun.sharma@snpsu.ac.in',
        'name':          'Arjun Sharma',
        'phone':         '+91 91234 56789',
        'club':          'Arts & Culture Society (ACS)',
        'password':      'SPOC@Arjun2026',
        'role':          'ClubSPOC',
        'category':      'Cultural',
        'whatsapp_group': 'https://chat.whatsapp.com/snpsu-acs-2026',
    },
    'sac': {
        'email':         'kavya.reddy@snpsu.ac.in',
        'name':          'Kavya Reddy',
        'phone':         '+91 87654 32109',
        'club':          'Student Activity Council (SAC)',
        'password':      'SPOC@Kavya2026',
        'role':          'ClubSPOC',
        'category':      'Sports',
        'whatsapp_group': 'https://chat.whatsapp.com/snpsu-sac-2026',
    },
}

# ──────────────────────────────────────────────────────────────
# BANNER IMAGES — Unsplash CDN
# ──────────────────────────────────────────────────────────────
BANNERS = {
    'hackathon':   'https://images.unsplash.com/photo-1519389950473-47ba0277781c?w=900&h=400&fit=crop',
    'coding':      'https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=900&h=400&fit=crop',
    'robotics':    'https://images.unsplash.com/photo-1485827404703-89b55fcc595e?w=900&h=400&fit=crop',
    'iot':         'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=900&h=400&fit=crop',
    'ai':          'https://images.unsplash.com/photo-1677442135703-1787eea5ce01?w=900&h=400&fit=crop',
    'webdev':      'https://images.unsplash.com/photo-1627398242454-45a1465c2479?w=900&h=400&fit=crop',
    'datascience': 'https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=900&h=400&fit=crop',
    'cybersec':    'https://images.unsplash.com/photo-1550751827-4bd374c3f58b?w=900&h=400&fit=crop',
    'appdev':      'https://images.unsplash.com/photo-1512941937669-90a1b58e7e9c?w=900&h=400&fit=crop',
    'cloud':       'https://images.unsplash.com/photo-1451187580459-43490279c0fa?w=900&h=400&fit=crop',
    'opensource':  'https://images.unsplash.com/photo-1556075798-4825dfaaf498?w=900&h=400&fit=crop',
    'algorithm':   'https://images.unsplash.com/photo-1509228468518-180dd4864904?w=900&h=400&fit=crop',
    'dance':       'https://images.unsplash.com/photo-1508700115892-45ecd05ae2ad?w=900&h=400&fit=crop',
    'music':       'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=900&h=400&fit=crop',
    'art':         'https://images.unsplash.com/photo-1541367777708-7905fe3296c0?w=900&h=400&fit=crop',
    'drama':       'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=900&h=400&fit=crop',
    'photography': 'https://images.unsplash.com/photo-1452587925148-ce544e77e70d?w=900&h=400&fit=crop',
    'film':        'https://images.unsplash.com/photo-1485846234645-a62644f84728?w=900&h=400&fit=crop',
    'singing':     'https://images.unsplash.com/photo-1516280440614-37939bbacd81?w=900&h=400&fit=crop',
    'rangoli':     'https://images.unsplash.com/photo-1604599340287-2042e85a3802?w=900&h=400&fit=crop',
    'cricket':     'https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=900&h=400&fit=crop',
    'badminton':   'https://images.unsplash.com/photo-1613918431703-aa50889e3be8?w=900&h=400&fit=crop',
    'chess':       'https://images.unsplash.com/photo-1529699211952-734e80c4d42b?w=900&h=400&fit=crop',
    'tabletennis': 'https://images.unsplash.com/photo-1534158914592-062992fbe900?w=900&h=400&fit=crop',
    'basketball':  'https://images.unsplash.com/photo-1546519638405-a9d1b37a4620?w=900&h=400&fit=crop',
    'volleyball':  'https://images.unsplash.com/photo-1592656094267-764a45160876?w=900&h=400&fit=crop',
    'startup':     'https://images.unsplash.com/photo-1552664730-d307ca884978?w=900&h=400&fit=crop',
    'marketing':   'https://images.unsplash.com/photo-1533750349088-cd871a92f312?w=900&h=400&fit=crop',
    'finance':     'https://images.unsplash.com/photo-1611974789855-9c2a0a7236a3?w=900&h=400&fit=crop',
    'debate':      'https://images.unsplash.com/photo-1475721027785-f74eccf877e2?w=900&h=400&fit=crop',
}

# ──────────────────────────────────────────────────────────────
# FORM SCHEMA BUILDERS
# ──────────────────────────────────────────────────────────────
YEARS = ['1st Year', '2nd Year', '3rd Year', '4th Year']


def _f(fid, ftype, label, required=False, placeholder='',
       options=None, help_text='', min_v='', max_v=''):
    return {
        'id':          fid,
        'type':        ftype,
        'label':       label,
        'placeholder': placeholder,
        'required':    required,
        'options':     options or [],
        'help_text':   help_text,
        'min':         min_v,
        'max':         max_v,
    }


def _heading(label):
    return _f('h_' + label.lower().replace(' ', '_').replace('/', '_'),
              'heading', label)


def _divider(n=''):
    return _f(f'divider{n}', 'divider', '')


def _leader_fields():
    return [
        _f('full_name',     'text',   'Full Name',            True,  'Enter your full name'),
        _f('email',         'email',  'Email Address',        True,  'you@college.edu'),
        _f('phone',         'tel',    'Phone / WhatsApp',     True,  '10-digit mobile number'),
        _f('usn',           'text',   'USN / Roll Number',    True,  'e.g. 1SN21CS001'),
        _f('year_of_study', 'select', 'Year of Study',        True,  '', YEARS),
        _f('branch',        'text',   'Branch / Department',  False, 'e.g. CSE, ECE, ME'),
    ]


def _member_fields(n, required=False):
    return [
        _divider(n),
        _heading(f'Member {n} Details'),
        _f(f'member_{n}_name',  'text',  f'Member {n} Full Name',      required, 'Full Name'),
        _f(f'member_{n}_email', 'email', f'Member {n} Email Address',  required, 'Email Address'),
        _f(f'member_{n}_usn',   'text',  f'Member {n} USN',            required, 'e.g. 1SN21CS001'),
        _f(f'member_{n}_phone', 'tel',   f'Member {n} Phone / WhatsApp', False,  'WhatsApp number'),
    ]


def _solo_schema(event_id, title, spoc_email):
    return {
        'event_id':   event_id,
        'form_type':  'simple',
        'form_title': f'Register — {title}',
        'form_desc':  'Fill in your details to register. A confirmation email will be sent.',
        'created_by': spoc_email,
        'updated_at': datetime.datetime.utcnow().isoformat(),
        'fields':     _leader_fields(),
    }


def _team_schema(event_id, title, spoc_email, team_min, team_max, allow_solo=False):
    num_slots = min(team_max - 1, 4)  # cap extra member slots at 4 for UX
    team_req  = not allow_solo

    fields = [
        _f('team_name', 'text', 'Team Name', team_req, 'Your team name',
           help_text=f'Min {team_min} – Max {team_max} members per team'),
        _divider(0),
        _heading('Team Leader Details'),
    ] + _leader_fields()

    for i in range(1, num_slots + 1):
        # Make member required only if team_min demands it
        member_req = (i < team_min) and not allow_solo
        fields += _member_fields(i, required=member_req)

    form_type = 'both' if allow_solo else 'team'
    if allow_solo:
        desc = (f'Register solo or as a team (up to {team_max} members) for {title}. '
                'Leave member fields blank for solo entry.')
    else:
        desc = (f'Register your team for {title}. '
                f'Min {team_min}, max {team_max} members. '
                'Confirmation sent to team leader.')

    return {
        'event_id':   event_id,
        'form_type':  form_type,
        'form_title': f'Register — {title}',
        'form_desc':  desc,
        'created_by': spoc_email,
        'updated_at': datetime.datetime.utcnow().isoformat(),
        'fields':     fields,
    }


def build_form_schema(event_id, title, spoc_email, part_type, team_min, team_max):
    if part_type == 'Solo':
        return _solo_schema(event_id, title, spoc_email)
    elif part_type == 'Team':
        return _team_schema(event_id, title, spoc_email, team_min, team_max, allow_solo=False)
    else:  # 'Both'
        return _team_schema(event_id, title, spoc_email, team_min, team_max, allow_solo=True)


# ──────────────────────────────────────────────────────────────
# EVENT FACTORY
# ──────────────────────────────────────────────────────────────
def make_event(title, category, banner_key, date, time, venue, description, rules,
               part_type, spoc_key,
               team_min=1, team_max=1, max_p=200,
               fee=0, prize1='₹5,000', prize2='₹3,000', prize3='₹1,500',
               years=None, reg_days_before=7):
    if years is None:
        years = [1, 2, 3, 4]
    spoc       = SPOCS[spoc_key]
    event_date = datetime.datetime.strptime(date, '%Y-%m-%d')
    deadline   = (event_date - datetime.timedelta(days=reg_days_before)).strftime('%Y-%m-%d')
    return {
        'title':              title,
        'category':           category,
        'description':        description,
        'rules':              rules,
        'banner_url':         BANNERS[banner_key],
        'visibility':         'Public',
        'date':               date,
        'time':               time,
        'reg_deadline':       deadline,
        'venue':              venue,
        'participation_type': part_type,
        'is_team_event':      part_type in ['Team', 'Both'],
        'coordinators':       [],
        'form_schema': {
            'require_lead_whatsapp':   True,
            'require_member_usn':      True,
            'require_member_email':    True,
            'require_member_whatsapp': True,
            'submission_type':         'none',
        },
        'limits': {
            'team_min':         team_min,
            'team_max':         team_max,
            'max_participants':  max_p,
            'allowed_years':     years,
        },
        'fees':               {'regular': fee},
        'prizes':             {'1st': prize1, '2nd': prize2, '3rd': prize3},
        'spoc_id':            spoc['email'],
        'organizer': {
            'name':       spoc['name'],
            'email':      spoc['email'],
            'phone':      spoc['phone'],
            'group_link': spoc['whatsapp_group'],
        },
        'status':             'active',
        'registration_count':  0,
        'results_published':   False,
        'has_custom_form':     True,
        'entry_fee':           fee,
        'created_at':          datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        # internal — used only during seeding, not persisted
        '_spoc_key':   spoc_key,
        '_part_type':  part_type,
        '_team_min':   team_min,
        '_team_max':   team_max,
    }


# ──────────────────────────────────────────────────────────────
# 30 EVENTS
# SPOC itc (Priya Nair)   → Technical × 12
# SPOC acs (Arjun Sharma) → Cultural × 8 + Management × 2
# SPOC sac (Kavya Reddy)  → Sports × 6 + Management × 2
# ──────────────────────────────────────────────────────────────
EVENTS = [

    # ── TECHNICAL — itc ─────────────────────────────────────────
    make_event(
        'HackathonX 2026', 'Technical', 'hackathon',
        '2026-05-10', '09:00 AM', 'Innovation Hub, Block A',
        '24-hour hackathon building innovative solutions to real-world problems. '
        'Themes: Smart Cities, HealthTech, EdTech, FinTech. '
        'Industry mentors guide teams throughout the event.',
        '1. Teams of 2–5.\n2. All code written during event.\n'
        '3. Open-source libraries allowed.\n4. Judged on innovation, completeness, presentation.',
        'Team', 'itc', 2, 5, 300, 150, '₹15,000', '₹10,000', '₹5,000',
    ),
    make_event(
        'Code Sprint Championship', 'Technical', 'coding',
        '2026-05-22', '10:00 AM', 'CS Lab 201, Block B',
        'Competitive programming contest — Screening, Semi-Final, and Grand Finale. '
        'Problems range from easy to expert level across algorithms, data structures, and maths.',
        '1. Individual only.\n2. Languages: C, C++, Python, Java.\n'
        '3. No internet access during contest.\n4. External IDEs not permitted.',
        'Solo', 'itc', 1, 1, 150, 50, '₹8,000', '₹5,000', '₹2,500',
    ),
    make_event(
        'Robo Wars 2026', 'Technical', 'robotics',
        '2026-06-05', '10:00 AM', 'Mechanical Lab Arena, Block C',
        'Build a remote-controlled combat robot and battle in the arena. '
        'Weight classes: Light (≤ 5 kg) and Heavy (≤ 15 kg).',
        '1. Teams of 3–5.\n2. Robot weight ≤ 15 kg.\n3. No liquid weapons.\n'
        '4. Safety kill switch mandatory.\n5. Arena damage = disqualification.',
        'Team', 'itc', 3, 5, 80, 300, '₹20,000', '₹12,000', '₹6,000',
    ),
    make_event(
        'IoT Innovation Challenge', 'Technical', 'iot',
        '2026-06-20', '09:30 AM', 'Electronics Lab, Block D',
        'Design and prototype an IoT solution for a campus or community problem. '
        'Arduino/Raspberry Pi hardware kits provided. Present a live demo to the jury.',
        '1. Teams of 2–4.\n2. Hardware kit provided; extras at own cost.\n'
        '3. Solution must be functional and demonstrated live.\n'
        '4. Open-source code must be shared on GitHub.',
        'Team', 'itc', 2, 4, 100, 100, '₹10,000', '₹6,000', '₹3,000',
    ),
    make_event(
        'AI & ML Showdown', 'Technical', 'ai',
        '2026-07-04', '09:00 AM', 'Data Science Lab, Block B',
        'Build and present an AI/ML model for a given dataset challenge. '
        'Dataset released 48 hours before the event. '
        'Judged on accuracy, creativity, and presentation clarity.',
        '1. Solo or pair (max 2).\n2. Python — sklearn/TensorFlow/PyTorch only.\n'
        '3. Pre-trained models allowed if credited.\n4. Notebooks submitted via Google Drive.',
        'Both', 'itc', 1, 2, 120, 75, '₹12,000', '₹7,000', '₹3,500',
    ),
    make_event(
        'Web Dev Showdown', 'Technical', 'webdev',
        '2026-07-18', '10:00 AM', 'Computer Lab 101, Block B',
        'Build a full-stack web application in 6 hours on a given theme. '
        'Deploy it live before the deadline. Teams present a 5-minute demo.',
        '1. Teams of 2–3.\n2. Frameworks: React, Vue, Django, Flask, Node.\n'
        '3. No pre-built templates — coded from scratch.\n4. App must be live.',
        'Team', 'itc', 2, 3, 100, 75, '₹8,000', '₹5,000', '₹2,000',
    ),
    make_event(
        'Data Science Olympiad', 'Technical', 'datascience',
        '2026-08-08', '09:30 AM', 'Data Science Lab, Block B',
        'Three-stage competition: Data Wrangling, Visualization Challenge, and Predictive Modelling. '
        'Real-world datasets from industry partners.',
        '1. Individual only.\n2. Python/R allowed.\n'
        '3. Internet for documentation only.\n4. Submit via Kaggle-style notebook.',
        'Solo', 'itc', 1, 1, 100, 50, '₹7,000', '₹4,000', '₹2,000',
    ),
    make_event(
        'CyberShield CTF', 'Technical', 'cybersec',
        '2026-08-22', '11:00 AM', 'Networking Lab, Block A',
        'Capture The Flag — Web, Forensics, Cryptography, Reverse Engineering, Pwn. '
        'Beginner to advanced difficulty. Category prizes plus overall leaderboard.',
        '1. Teams of 1–4.\n2. No attacking shared infrastructure.\n'
        '3. Flag sharing = disqualification.\n4. Hint system penalises score.',
        'Both', 'itc', 1, 4, 200, 100, '₹10,000', '₹6,000', '₹3,000',
    ),
    make_event(
        'App Dev Challenge', 'Technical', 'appdev',
        '2026-09-05', '10:00 AM', 'Innovation Hub, Block A',
        'Design and develop a mobile app (Android/iOS/PWA) in 8 hours. '
        'Theme announced on the day. Judged on UX, functionality, and innovation.',
        '1. Teams of 2–4.\n2. Flutter, React Native, or native allowed.\n'
        '3. App must demo on a physical device.\n4. Firebase backend recommended.',
        'Team', 'itc', 2, 4, 80, 100, '₹9,000', '₹5,500', '₹2,500',
    ),
    make_event(
        'Cloud Computing Bootcamp & Contest', 'Technical', 'cloud',
        '2026-09-19', '09:00 AM', 'Server Room Lab, Block A',
        'Morning: 3-hour hands-on AWS/GCP workshop (free for all). '
        'Afternoon: speed challenge on cloud deployment tasks. AWS Educate credits provided.',
        '1. Individual only.\n2. Bring laptop.\n'
        '3. Free-tier cloud accounts provided in advance.\n4. Workshop attendance mandatory.',
        'Solo', 'itc', 1, 1, 150, 0,
        '₹5,000 + AWS credits', '₹3,000 + AWS credits', '₹1,500 + AWS credits',
    ),
    make_event(
        'Open Source Sprint', 'Technical', 'opensource',
        '2026-10-03', '10:00 AM', 'Computer Lab 202, Block B',
        'Contribute to curated open-source repos in a 6-hour sprint. '
        'Points for merged PRs, bug fixes, and documentation. All skill levels welcome.',
        '1. Individual only.\n2. Contributions must be merged by event end.\n'
        '3. Only labelled issues count.\n4. AI-generated code without understanding = disqualified.',
        'Solo', 'itc', 1, 1, 200, 0,
        '₹4,000 + certificate', '₹2,500 + certificate', '₹1,000 + certificate',
    ),
    make_event(
        'Algorithm Arena', 'Technical', 'algorithm',
        '2026-10-17', '10:00 AM', 'CS Lab 101, Block B',
        'Head-to-head algorithm battles. Single-elimination tournament. '
        'First correct solution per round advances.',
        '1. Individual only.\n2. Languages: C++, Python, Java.\n'
        '3. 20-minute time limit per round.\n4. One submission attempt per round.',
        'Solo', 'itc', 1, 1, 64, 50, '₹6,000', '₹3,500', '₹1,500',
    ),

    # ── CULTURAL + MANAGEMENT — acs ─────────────────────────────
    make_event(
        'Rhythm Rush — Solo Dance', 'Cultural', 'dance',
        '2026-05-30', '02:00 PM', 'Main Auditorium',
        'Showcase dance talent — Classical, Contemporary, Hip-Hop, or Freestyle. '
        '3-minute solo performance judged on technique, expression, and stage presence.',
        '1. Solo — 3 minutes max.\n2. Music track submitted 2 days before.\n'
        '3. Decent, college-appropriate costumes.\n4. Safe props allowed.',
        'Solo', 'acs', 1, 1, 60, 50,
        '₹5,000 + Trophy', '₹3,000 + Trophy', '₹1,500 + Trophy',
    ),
    make_event(
        'Battle of Bands', 'Cultural', 'music',
        '2026-06-14', '05:00 PM', 'Open Air Theatre',
        'Inter-college band competition. Two songs — one original composition and one cover. '
        '20 minutes per band including setup.',
        '1. Bands of 3–8.\n2. Instruments must be brought (basic PA provided).\n'
        '3. No explicit lyrics.\n4. College ID mandatory for all members.',
        'Team', 'acs', 3, 8, 120, 200, '₹25,000', '₹15,000', '₹8,000',
    ),
    make_event(
        'Canvas & Colors — Painting', 'Cultural', 'art',
        '2026-07-11', '10:00 AM', 'Art Studio, Block E',
        'On-spot painting — theme revealed 15 min before start. '
        '3-hour session. All mediums: watercolour, acrylic, oil pastel.',
        '1. Individual only.\n2. Canvas (A2) provided.\n'
        '3. Bring own paints and brushes.\n4. Must relate to announced theme.',
        'Solo', 'acs', 1, 1, 80, 50, '₹4,000', '₹2,500', '₹1,000',
    ),
    make_event(
        'Drama Quest — Theatre Competition', 'Cultural', 'drama',
        '2026-07-25', '03:00 PM', 'Main Auditorium',
        'Short play competition on socially relevant themes. 10–15 minute performances.',
        '1. Teams of 5–12.\n2. Themes: Environment, Gender Equality, Mental Health, Technology.\n'
        '3. Original scripts.\n4. English, Hindi, or Kannada.',
        'Team', 'acs', 5, 12, 150, 100, '₹12,000', '₹7,000', '₹3,500',
    ),
    make_event(
        'Click & Capture — Photography', 'Cultural', 'photography',
        '2026-08-15', '08:00 AM', 'SNPSU Campus (Outdoor)',
        'Campus photography walk — theme "Everyday Life on Campus." '
        'Submit best 3 shots by 12 PM.',
        '1. Individual only.\n2. DSLR, mirrorless, or smartphone allowed.\n'
        '3. Basic edits only — no compositing.\n4. Submit 3 JPEGs via Google Drive by noon.',
        'Solo', 'acs', 1, 1, 100, 0,
        '₹4,500 + framed print', '₹2,500 + framed print', '₹1,000 + framed print',
    ),
    make_event(
        'Short Film Fiesta', 'Cultural', 'film',
        '2026-09-12', '10:00 AM', 'Media Lab & Auditorium, Block F',
        '48-hour short film challenge. Theme given Friday evening; films screened Sunday. '
        '5–10 minutes, original footage only.',
        '1. Teams of 3–8.\n2. All footage shot after theme announcement.\n'
        '3. Submit MP4 (1080p min) via Google Drive.\n4. Subtitles required if not in English.',
        'Team', 'acs', 3, 8, 80, 150, '₹15,000', '₹9,000', '₹4,500',
    ),
    make_event(
        'Singing Idol — Vocal Contest', 'Cultural', 'singing',
        '2026-10-09', '04:00 PM', 'Main Auditorium',
        'Solo vocal contest — Screening (recorded), Semi-Final (live), '
        'Grand Finale (live with band). Any language, any genre.',
        '1. Solo only.\n2. Karaoke track allowed in preliminary.\n'
        '3. 4-minute time limit.\n4. Venue mic mandatory.',
        'Solo', 'acs', 1, 1, 80, 50,
        '₹8,000 + Trophy', '₹5,000 + Trophy', '₹2,000 + Trophy',
    ),
    make_event(
        'Rangoli Royale', 'Cultural', 'rangoli',
        '2026-10-31', '09:00 AM', 'College Corridor, Block A',
        'Traditional and contemporary Rangoli — theme "Festivals of India." 3-hour creation.',
        '1. Teams of 2–4.\n2. Colours provided; extra materials at own cost.\n'
        '3. No pre-drawn outlines.\n4. Area: 5 × 5 feet per team.',
        'Team', 'acs', 2, 4, 60, 50, '₹3,000', '₹2,000', '₹1,000',
    ),
    make_event(
        'Startup Pitch Battle', 'Management', 'startup',
        '2026-05-16', '10:00 AM', 'Seminar Hall 1, Block A',
        'Pitch your startup idea to investors and mentors. '
        '5 min pitch + 5 min Q&A. Judged on problem-market fit, feasibility, and scalability.',
        '1. Teams of 2–5.\n2. Pitch deck (max 10 slides) submitted 2 days before.\n'
        '3. Working MVP is a bonus.\n4. Original ideas only.',
        'Team', 'acs', 2, 5, 120, 100,
        '₹20,000 + Incubation', '₹10,000', '₹5,000',
    ),
    make_event(
        'Marketing Maestros', 'Management', 'marketing',
        '2026-07-30', '10:00 AM', 'Seminar Hall 2, Block A',
        'Create a full marketing campaign for a fictional product — research, branding, '
        'digital strategy, and budget. Present in 10 minutes to a jury.',
        '1. Teams of 3–5.\n2. Product brief revealed 2 hours before presentations.\n'
        '3. PowerPoint/Canva only.\n4. Budget: fictional ₹10 lakh.',
        'Team', 'acs', 3, 5, 80, 75, '₹8,000', '₹5,000', '₹2,500',
    ),

    # ── SPORTS + MANAGEMENT — sac ────────────────────────────────
    make_event(
        'Cricket Carnival', 'Sports', 'cricket',
        '2026-06-07', '07:00 AM', 'SNPSU Cricket Ground',
        'Inter-department T10 cricket tournament. Knockout format. Up to 12 departments.',
        '1. Teams of 11 + 2 substitutes.\n2. T10 format — 10 overs per side.\n'
        '3. Valid college ID mandatory.\n4. Umpires\' decision is final.\n'
        '5. Helmets and pads mandatory for batsmen.',
        'Team', 'sac', 11, 13, 150, 500,
        '₹20,000 + Trophy', '₹12,000 + Trophy', '₹0',
    ),
    make_event(
        'Badminton Blast', 'Sports', 'badminton',
        '2026-07-02', '08:00 AM', 'Indoor Sports Hall',
        'Singles and doubles badminton tournament. Men\'s Singles and Mixed Doubles categories.',
        '1. Open to all SNPSU students.\n2. Bring own rackets.\n'
        '3. Shuttle provided.\n4. BWF rules apply.',
        'Both', 'sac', 1, 2, 100, 100,
        '₹4,000 per category', '₹2,000 per category', '₹0',
    ),
    make_event(
        'Chess Masters Championship', 'Sports', 'chess',
        '2026-08-01', '10:00 AM', 'Seminar Hall 3, Block D',
        'Swiss-system chess tournament (7 rounds). Time control: 15+5 rapid. FIDE rules.',
        '1. Individual only.\n2. Devices off during games.\n'
        '3. Draws by agreement after move 30 only.\n4. Arbiter\'s decision is final.',
        'Solo', 'sac', 1, 1, 64, 50,
        '₹5,000 + Chess set', '₹3,000', '₹1,500',
    ),
    make_event(
        'Table Tennis Tussle', 'Sports', 'tabletennis',
        '2026-08-28', '09:00 AM', 'Indoor Sports Hall',
        'Singles table tennis. Knockout + round-robin group stage. Best of 5 sets. ITTF rules.',
        '1. Individual only.\n2. Own bats allowed (no illegal rubbers).\n'
        '3. SNPSU-branded balls used.\n4. Referee\'s call is final.',
        'Solo', 'sac', 1, 1, 64, 50, '₹3,500', '₹2,000', '₹1,000',
    ),
    make_event(
        'Basketball Bonanza 3×3', 'Sports', 'basketball',
        '2026-09-26', '08:00 AM', 'Basketball Court, SNPSU',
        '3-on-3 basketball (FIBA 3×3 rules). Separate brackets for men and women. '
        'Round-robin pool stage + knockout semis and finals.',
        '1. Teams of 3 + 1 substitute.\n2. FIBA 3×3 rules — 10-minute games.\n'
        '3. Basketball shoes mandatory.\n4. No jewellery during play.',
        'Team', 'sac', 3, 4, 120, 200,
        '₹8,000 per bracket', '₹4,500 per bracket', '₹0',
    ),
    make_event(
        'Volleyball Vibe', 'Sports', 'volleyball',
        '2026-10-24', '08:30 AM', 'Volleyball Court, SNPSU',
        'Inter-department volleyball — 6-a-side, knockout format. Up to 10 department teams.',
        '1. Teams of 6 + 2 substitutes.\n2. FIVB rules.\n'
        '3. Knee pads recommended.\n4. Only registered players on court.',
        'Team', 'sac', 6, 8, 100, 300,
        '₹10,000 + Trophy', '₹6,000', '₹0',
    ),
    make_event(
        'Finance Quiz Bowl', 'Management', 'finance',
        '2026-09-05', '02:00 PM', 'Seminar Hall 3, Block D',
        'Three-round finance quiz: Written, Rapid Fire, and Audio-Visual. '
        'Topics: stock markets, corporate finance, banking, global economy.',
        '1. Teams of 2.\n2. No phones during quiz.\n'
        '3. Quizmaster\'s decision is final.\n4. Negative marking in written round.',
        'Team', 'sac', 2, 2, 100, 50, '₹6,000', '₹3,500', '₹1,500',
    ),
    make_event(
        'Model UN — Campus Debate', 'Management', 'debate',
        '2026-10-10', '09:00 AM', 'Seminar Hall 1 & 2, Block A',
        'One-day MUN simulation — UNSC, UNGA, WHO, ECOSOC. '
        'Delegates represent assigned countries. Awards per committee.',
        '1. Individual delegates — register with country/committee preference.\n'
        '2. Position paper submitted 1 week before.\n3. Formal attire mandatory.\n'
        '4. Rules of procedure strictly followed.',
        'Solo', 'sac', 1, 1, 120, 150,
        'Best Delegate + ₹2,000', 'Outstanding Delegate + ₹1,000',
        'Honourable Mention + certificate',
    ),
]


# ──────────────────────────────────────────────────────────────
# SEED FUNCTIONS
# ──────────────────────────────────────────────────────────────
def create_spocs():
    created = 0
    for key, spoc in SPOCS.items():
        ref = db.collection('users').document(spoc['email'])
        if ref.get().exists:
            print(f"  ⚠  SPOC already exists: {spoc['email']} — skipping.")
            continue
        ref.set({
            'email':                spoc['email'],
            'name':                 spoc['name'],
            'phone':                spoc['phone'],
            'role':                 spoc['role'],
            'category':             spoc['category'],
            'club':                 spoc['club'],
            'password':             generate_password_hash(spoc['password']),
            'created_at':           datetime.datetime.now().strftime('%Y-%m-%d'),
            'needs_password_reset': False,
        })
        print(f"  ✅ SPOC created: {spoc['name']} ({spoc['email']})")
        created += 1
    return created


def seed_events():
    ev_created, form_created = 0, 0
    for ev in EVENTS:
        # Pop internal keys before saving
        spoc_key  = ev.pop('_spoc_key')
        part_type = ev.pop('_part_type')
        team_min  = ev.pop('_team_min')
        team_max  = ev.pop('_team_max')

        spoc_email = SPOCS[spoc_key]['email']

        _, ref = db.collection('events').add(ev)
        event_id = ref.id
        print(f"  ✅ [{ev['category']:12s}] {ev['title']}  →  {event_id}")
        ev_created += 1

        # Build and save matching form schema
        schema = build_form_schema(event_id, ev['title'], spoc_email,
                                   part_type, team_min, team_max)
        db.collection('event_forms').document(event_id).set(schema)
        form_type_label = schema['form_type']
        print(f"       └─ form: {form_type_label}  ({len(schema['fields'])} fields)")
        form_created += 1

    return ev_created, form_created


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if db is None:
        print("❌ Firestore not connected. Check serviceAccountKey.json.")
        sys.exit(1)

    print("\n══════════════════════════════════════════════════════")
    print("  SNPSU Event Portal — Seed Script")
    print("══════════════════════════════════════════════════════\n")

    print("1/2  Creating 3 Club SPOC accounts …")
    create_spocs()

    print(f"\n2/2  Seeding {len(EVENTS)} events + registration forms …")
    n_ev, n_forms = seed_events()

    print(f"\n══════════════════════════════════════════════════════")
    print(f"  Done!  {n_ev} events + {n_forms} event_forms seeded.")
    print()

    for key, s in SPOCS.items():
        print(f"  ┌─ {s['club']}")
        print(f"  │  Name     : {s['name']}")
        print(f"  │  Email    : {s['email']}")
        print(f"  │  Password : {s['password']}")
        print(f"  │  Role     : ClubSPOC  (category: {s['category']})")
        print(f"  │  Phone    : {s['phone']}")
        print(f"  └──────────────────────────────────────────────")
        print()
