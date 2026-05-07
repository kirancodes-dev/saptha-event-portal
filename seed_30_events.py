"""
seed_30_events.py
Creates 3 SPOCs + 30 events (10 each: Cultural, Sports, Technical).
Date spread: tomorrow, +3 days, +4 days.
Media: banner image + 1 video per event.
Paid: 3 events (1 per category). Rest are free.
No judges, coordinators, or students loaded.
"""

import sys
import datetime
sys.path.insert(0, '.')

from models import db
from werkzeug.security import generate_password_hash
from datetime import date, timedelta

TODAY      = date.today()
TOMORROW   = str(TODAY + timedelta(days=1))
PLUS3      = str(TODAY + timedelta(days=3))
PLUS4      = str(TODAY + timedelta(days=4))
DEADLINE_0 = str(TODAY)                         # reg closed today  (for tomorrow events)
DEADLINE_2 = str(TODAY + timedelta(days=2))     # 2 days away
DEADLINE_3 = str(TODAY + timedelta(days=3))     # 3 days away
NOW        = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── SPOC accounts ──────────────────────────────────────────
SPOCS = [
    {
        'email':    'cultural.spoc@snpsu.edu.in',
        'name':     'Meera Sharma',
        'password': 'Cultural@2026',
        'role':     'ClubSPOC',
        'category': 'Cultural',
        'club':     'Cultural Arts Club',
    },
    {
        'email':    'sports.spoc@snpsu.edu.in',
        'name':     'Arjun Reddy',
        'password': 'Sports@2026',
        'role':     'ClubSPOC',
        'category': 'Sports',
        'club':     'Sports Association',
    },
    {
        'email':    'tech.spoc@snpsu.edu.in',
        'name':     'Priya Nair',
        'password': 'Tech@2026',
        'role':     'ClubSPOC',
        'category': 'Tech',
        'club':     'Technical Developers Club',
    },
]

# ── Image + Video URLs ─────────────────────────────────────
# Picsum seeds are deterministic (same seed → same image always)
def img(seed, w=800, h=400):
    return f'https://picsum.photos/seed/{seed}/{w}/{h}'

# Free sample MP4 videos (public domain)
VIDS = {
    'cultural': 'https://www.w3schools.com/html/mov_bbb.mp4',
    'sports':   'https://www.learningcontainer.com/wp-content/uploads/2020/05/sample-mp4-file.mp4',
    'tech':     'https://www.w3schools.com/html/movie.mp4',
}

# ── Helper ─────────────────────────────────────────────────
def make_event(title, category, spoc_id, spoc_name, spoc_email,
               date_str, deadline_str, time_str, venue,
               description, rules, prizes, reg_fee,
               banner_seed, extra_img_seed,
               participation_type='Individual', is_team=False,
               team_min=1, team_max=1, max_p=200):
    vid = VIDS.get(category.lower(), VIDS['tech'])
    return {
        'title':            title,
        'category':         category,
        'description':      description,
        'rules':            rules,
        'banner_url':       img(banner_seed),
        'media_urls':       [img(banner_seed), img(extra_img_seed), vid],
        'visibility':       'Public',
        'date':             date_str,
        'time':             time_str,
        'reg_deadline':     deadline_str,
        'venue':            venue,
        'participation_type': participation_type,
        'is_team_event':    is_team,
        'coordinators':     [],
        'form_schema': {
            'require_lead_whatsapp':    False,
            'require_member_usn':       is_team,
            'require_member_email':     False,
            'require_member_whatsapp':  False,
            'submission_type':          'none',
        },
        'limits': {
            'team_min':        team_min,
            'team_max':        team_max,
            'max_participants': max_p,
            'allowed_years':   [1, 2, 3, 4],
        },
        'fees':   {'regular': reg_fee},
        'prizes': prizes,
        'spoc_id': spoc_id,
        'organizer': {
            'name':       spoc_name,
            'email':      spoc_email,
            'phone':      '9876543210',
            'group_link': '#',
        },
        'status':           'active',
        'created_at':       NOW,
        'results_published': False,
        'open_hall_mode':   False,
        'has_custom_form':  False,
    }


# ═══════════════════════════════════════════════════════════
# MAIN SEED
# ═══════════════════════════════════════════════════════════
def run():
    # 1. Create / overwrite SPOC users
    spoc_ids = {}
    for s in SPOCS:
        db.collection('users').document(s['email']).set({
            'name':      s['name'],
            'email':     s['email'],
            'password':  generate_password_hash(s['password']),
            'role':      s['role'],
            'category':  s['category'],
            'club':      s['club'],
            'created_at': NOW,
        })
        spoc_ids[s['category']] = s['email']
        print(f"  SPOC created: {s['name']} ({s['category']}) — {s['email']} / {s['password']}")

    cultural_id   = spoc_ids['Cultural']
    sports_id     = spoc_ids['Sports']
    tech_id       = spoc_ids['Tech']
    cultural_name = SPOCS[0]['name']
    sports_name   = SPOCS[1]['name']
    tech_name     = SPOCS[2]['name']

    # ── 2. Define 30 events ──────────────────────────────
    events = []

    # ── CULTURAL (10) ─────────────────────────────────────
    events += [
        # Tomorrow (reg deadline = today)
        make_event(
            title='Solo Singing Championship', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='10:00',
            venue='Main Auditorium', reg_fee=0,
            description='Showcase your vocal talent in this solo singing contest open to all years. Classical, semi-classical, film, and indie genres all welcome.',
            rules='1. Performance max 5 min.\n2. Own instrument or karaoke allowed.\n3. No explicit content.\n4. Decision of judges is final.',
            prizes={'1st': '₹5,000 Cash + Trophy', '2nd': '₹3,000 Cash', '3rd': '₹2,000 Cash'},
            banner_seed='singing', extra_img_seed='music-stage',
            participation_type='Individual', max_p=150,
        ),
        make_event(
            title='Street Play Festival', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='11:00',
            venue='Open Air Theatre', reg_fee=0,
            description='A high-energy street play (Nukkad Natak) competition addressing social issues. Teams of 8–15 members perform for 10–15 minutes.',
            rules='1. Team size: 8–15 members.\n2. Duration: 10–15 minutes.\n3. Props allowed, no live fire or smoke.\n4. Theme must be socially relevant.',
            prizes={'1st': '₹8,000 + Rolling Trophy', '2nd': '₹5,000', '3rd': '₹3,000'},
            banner_seed='street-play', extra_img_seed='theatre',
            participation_type='Team', is_team=True, team_min=8, team_max=15, max_p=120,
        ),
        make_event(
            title='Photography Showdown', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='09:00',
            venue='Block B Corridor & Campus', reg_fee=0,
            description='Capture the soul of the campus in this 3-hour on-spot photography hunt. Theme announced at the start of the event.',
            rules='1. Only mobile/DSLR cameras allowed.\n2. No heavy post-processing — basic exposure/colour correction only.\n3. Submit 3 best shots in JPEG before deadline.\n4. Plagiarism = disqualification.',
            prizes={'1st': 'Professional Camera Kit', '2nd': '₹3,000', '3rd': '₹1,500'},
            banner_seed='photography', extra_img_seed='camera-lens',
            participation_type='Individual', max_p=100,
        ),

        # +3 days
        make_event(
            title='Group Dance Championship', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='14:00',
            venue='Main Auditorium', reg_fee=0,
            description='Battle it out on stage with your crew in this electrifying group dance competition. All styles — classical, folk, hip-hop, fusion — accepted.',
            rules='1. Team size: 5–20 members.\n2. Performance: 5–10 min.\n3. Music to be submitted 2 days prior.\n4. No offensive gestures.',
            prizes={'1st': '₹12,000 + Revolving Shield', '2nd': '₹7,000', '3rd': '₹4,000'},
            banner_seed='dance-group', extra_img_seed='dance-stage',
            participation_type='Team', is_team=True, team_min=5, team_max=20, max_p=200,
        ),
        make_event(
            title='Poetry Slam & Spoken Word', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='16:00',
            venue='Seminar Hall 2', reg_fee=0,
            description='An evening of raw, unfiltered expression. Write, perform, and move the audience through the power of words — Hindi, English, or Kannada.',
            rules='1. Original compositions only.\n2. Performance: 3–5 min.\n3. No offensive language targeting individuals.\n4. Audience scoring included.',
            prizes={'1st': '₹4,000', '2nd': '₹2,500', '3rd': '₹1,500'},
            banner_seed='poetry', extra_img_seed='microphone',
            participation_type='Individual', max_p=80,
        ),
        make_event(
            title='Fine Arts Exhibition', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='10:00',
            venue='Art Block Gallery', reg_fee=0,
            description='Present your artwork — painting, sculpture, digital art, or installations — in an open gallery format. Judged on creativity, execution, and theme relevance.',
            rules='1. Artwork must be original and brought on the day.\n2. Canvas size max 3×3 ft.\n3. 3D works must be self-supporting.\n4. Artist present for Q&A.',
            prizes={'1st': '₹5,000 + Certificate', '2nd': '₹3,000', '3rd': '₹2,000'},
            banner_seed='fine-arts', extra_img_seed='painting',
            participation_type='Individual', max_p=60,
        ),

        # +4 days  — 1 PAID event here
        make_event(
            title='Fashion Show Extravaganza', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='18:00',
            venue='Main Auditorium', reg_fee=300,   # ← PAID
            description='The most glamorous event of the year! Walk the ramp with sustainable fashion, traditional attire, or futuristic couture. Make a statement.',
            rules='1. Team of 2–6 members.\n2. Theme: Sustainable Chic.\n3. Original outfits only — no rental costumes.\n4. 8-minute runway slot per team.',
            prizes={'1st': '₹15,000 + Crown', '2nd': '₹10,000', '3rd': '₹6,000'},
            banner_seed='fashion-show', extra_img_seed='runway',
            participation_type='Team', is_team=True, team_min=2, team_max=6, max_p=80,
        ),
        make_event(
            title='Classical Dance Recital', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='11:00',
            venue='Seminar Hall 1', reg_fee=0,
            description='A solo or duet classical dance recital open to Bharatanatyam, Kathak, Odissi, Kuchipudi, Mohiniyattam, and other classical Indian forms.',
            rules='1. Solo or duet only.\n2. Duration: 5–8 min.\n3. Costume as per the classical form.\n4. Music provided on CD/pen drive.',
            prizes={'1st': '₹6,000', '2nd': '₹4,000', '3rd': '₹2,000'},
            banner_seed='classical-dance', extra_img_seed='bharatanatyam',
            participation_type='Individual', max_p=60,
        ),
        make_event(
            title='Open Mic Night', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='19:00',
            venue='Open Air Theatre', reg_fee=0,
            description='Comedy, storytelling, stand-up, poetry, or music — the mic is yours for 5 minutes. A casual, judgment-free evening of creative expression.',
            rules='1. Max 5 minutes per slot.\n2. No offensive/hate content.\n3. First come, first served.\n4. Arrive 30 min before start.',
            prizes={'1st': 'No ranks — Top 3 audience picks get goodies!', '2nd': '', '3rd': ''},
            banner_seed='open-mic', extra_img_seed='stage-lights',
            participation_type='Individual', max_p=200,
        ),
        make_event(
            title='Drama Fest — One-Act Play', category='Cultural',
            spoc_id=cultural_id, spoc_name=cultural_name, spoc_email=cultural_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='15:00',
            venue='Main Auditorium', reg_fee=0,
            description='Write, direct, and perform an original one-act play. Any genre — comedy, tragedy, thriller. Teams of 5–12 members compete for the Curtain Call Trophy.',
            rules='1. Team: 5–12 members.\n2. Duration: 15–25 min.\n3. Script to be submitted 3 days before.\n4. Minimal props provided by organisers.',
            prizes={'1st': '₹10,000 + Trophy', '2nd': '₹6,000', '3rd': '₹3,000'},
            banner_seed='drama-theatre', extra_img_seed='play-stage',
            participation_type='Team', is_team=True, team_min=5, team_max=12, max_p=100,
        ),
    ]

    # ── SPORTS (10) ───────────────────────────────────────
    events += [
        # Tomorrow
        make_event(
            title='3x3 Basketball Blitz', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='08:00',
            venue='Sports Complex — Basketball Court', reg_fee=0,
            description='Fast-paced 3-on-3 basketball tournament. Half-court, 10-minute timed games. Knockout format. Both men and women divisions.',
            rules='1. Teams of 3 + 1 substitute.\n2. FIBA 3x3 rules apply.\n3. Proper sports shoes mandatory.\n4. No jewellery on court.',
            prizes={'1st': '₹6,000 + Medals', '2nd': '₹4,000', '3rd': '₹2,000'},
            banner_seed='basketball', extra_img_seed='basketball-court',
            participation_type='Team', is_team=True, team_min=3, team_max=4, max_p=120,
        ),
        make_event(
            title='Badminton Open Championship', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='09:00',
            venue='Indoor Sports Hall', reg_fee=0,
            description='Singles and doubles badminton knockout tournament. Separate categories for men and women. BWF rules strictly followed.',
            rules='1. Own rackets; shuttles provided.\n2. Best of 3 games, 21 points each.\n3. Proper sports attire required.\n4. Punctuality mandatory — no-show = walkover.',
            prizes={'1st': '₹5,000', '2nd': '₹3,000', '3rd': '₹1,500'},
            banner_seed='badminton', extra_img_seed='indoor-sports',
            participation_type='Individual', max_p=160,
        ),
        make_event(
            title='Table Tennis Lightning', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='10:00',
            venue='Indoor Sports Hall — TT Zone', reg_fee=0,
            description='Singles table tennis speed tournament with 5-minute match slots. Best reflexes win. Round-robin pool stage + knockouts.',
            rules='1. ITTF rules.\n2. Own paddle allowed; balls provided.\n3. 11-point games, best of 5.\n4. Report 15 min before your slot.',
            prizes={'1st': '₹3,000', '2nd': '₹2,000', '3rd': '₹1,000'},
            banner_seed='table-tennis', extra_img_seed='ping-pong',
            participation_type='Individual', max_p=80,
        ),

        # +3 days — 1 PAID event here
        make_event(
            title='Cricket T10 Smash', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='07:30',
            venue='College Ground', reg_fee=200,  # ← PAID
            description='T10 format cricket tournament across two days. Teams of 11 + 4 substitutes. Full day knockout with final played on day 2.',
            rules='1. T10 rules — 10 overs per side.\n2. Tennis ball; team provides own bat.\n3. Player ID mandatory at registration.\n4. No spikes allowed on ground.',
            prizes={'1st': '₹20,000 + Trophy', '2nd': '₹12,000', '3rd': '₹6,000'},
            banner_seed='cricket', extra_img_seed='cricket-ground',
            participation_type='Team', is_team=True, team_min=11, team_max=15, max_p=200,
        ),
        make_event(
            title='Volleyball Tournament', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='09:00',
            venue='Volleyball Courts', reg_fee=0,
            description='6-a-side volleyball league with pool stage and knockouts. Men and women divisions. FIVB rules apply.',
            rules='1. Team of 6 + 2 substitutes.\n2. 25-point rally scoring.\n3. Best of 3 sets.\n4. Proper sports shoes required.',
            prizes={'1st': '₹8,000', '2nd': '₹5,000', '3rd': '₹2,500'},
            banner_seed='volleyball', extra_img_seed='volleyball-team',
            participation_type='Team', is_team=True, team_min=6, team_max=8, max_p=150,
        ),
        make_event(
            title='Chess Masters Cup', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='11:00',
            venue='Seminar Hall 3', reg_fee=0,
            description='Swiss-system chess tournament over 7 rounds. Clock time: 15+10 (15 min + 10-sec increment). Top 3 qualify for inter-collegiate.',
            rules='1. FIDE rules strictly.\n2. Phones off during game.\n3. Touch piece = move piece.\n4. Tie-break: Buchholz score.',
            prizes={'1st': '₹4,000', '2nd': '₹2,500', '3rd': '₹1,500'},
            banner_seed='chess', extra_img_seed='chess-board',
            participation_type='Individual', max_p=64,
        ),

        # +4 days
        make_event(
            title='Football 5-A-Side Cup', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='07:00',
            venue='Football Ground', reg_fee=0,
            description='5-a-side football knockout. 15-minute halves on a reduced pitch. Fast, technical, and exciting. Co-ed teams allowed.',
            rules='1. Team of 5 + 2 subs.\n2. No sliding tackles.\n3. Futsal-style rules.\n4. Referee decision is final.',
            prizes={'1st': '₹10,000', '2nd': '₹6,000', '3rd': '₹3,000'},
            banner_seed='football', extra_img_seed='soccer-field',
            participation_type='Team', is_team=True, team_min=5, team_max=7, max_p=140,
        ),
        make_event(
            title='Athletics Track & Field', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='06:30',
            venue='Athletics Track', reg_fee=0,
            description='Track and field events: 100 m, 200 m, 400 m, 4×100 m relay, long jump, shot put, and high jump. Multiple events per participant allowed.',
            rules='1. Proper track shoes or bare feet only — no block heels.\n2. Two false starts = disqualification.\n3. Qualify in heats for finals.',
            prizes={'1st': 'Gold Medal + ₹2,000', '2nd': 'Silver + ₹1,500', '3rd': 'Bronze + ₹1,000'},
            banner_seed='athletics-track', extra_img_seed='running',
            participation_type='Individual', max_p=300,
        ),
        make_event(
            title='Kabaddi League', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='09:00',
            venue='Kabaddi Ground', reg_fee=0,
            description='Traditional Indian Kabaddi with standard mat rules. 40-minute matches. Teams of 7 on mat. Exciting raider vs. defender action.',
            rules='1. Standard Kabaddi Federation rules.\n2. Team: 7 on mat + 5 off.\n3. Raider must chant "kabaddi" continuously.\n4. No holding the raider by hair or clothing collar.',
            prizes={'1st': '₹7,000', '2nd': '₹4,000', '3rd': '₹2,000'},
            banner_seed='kabaddi', extra_img_seed='sports-team',
            participation_type='Team', is_team=True, team_min=7, team_max=12, max_p=120,
        ),
        make_event(
            title='Swimming Gala', category='Sports',
            spoc_id=sports_id, spoc_name=sports_name, spoc_email=sports_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='08:00',
            venue='SNPSU Swimming Pool', reg_fee=0,
            description='Swimming competition across freestyle (50 m, 100 m), backstroke (50 m), breaststroke (50 m), and 4×50 m medley relay.',
            rules='1. FINA rules.\n2. Swimwear and cap mandatory.\n3. No dive starts in backstroke.\n4. One event per swimmer (except relay).',
            prizes={'1st': '₹3,000 per event', '2nd': '₹2,000', '3rd': '₹1,000'},
            banner_seed='swimming', extra_img_seed='pool',
            participation_type='Individual', max_p=100,
        ),
    ]

    # ── TECHNICAL (10) ────────────────────────────────────
    events += [
        # Tomorrow
        make_event(
            title='Hackathon 2026 — Build the Future', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='08:00',
            venue='Computer Science Block — Labs 1–5', reg_fee=500,  # ← PAID
            description='24-hour hackathon challenging teams to build real solutions in AI, healthcare, sustainability, or smart cities. Mentors, cloud credits, and hardware available on-site.',
            rules='1. Teams of 3–5.\n2. Code must be written during hackathon (open source libs OK).\n3. Repo pushed to GitHub by deadline.\n4. 5-minute demo + 2-minute Q&A.',
            prizes={'1st': '₹30,000 + AWS Credits', '2nd': '₹15,000', '3rd': '₹8,000'},
            banner_seed='hackathon', extra_img_seed='coding-laptops',
            participation_type='Team', is_team=True, team_min=3, team_max=5, max_p=200,
        ),
        make_event(
            title='Code Sprint — 2 Hour Challenge', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='14:00',
            venue='CS Lab Block — Room 202', reg_fee=0,
            description='Competitive programming contest with 6 algorithmic problems across easy, medium, and hard tiers. Languages: C++, Java, Python, or Kotlin.',
            rules='1. Individual only.\n2. No internet access allowed (IDE + stdlib only).\n3. Penalty +5 min per wrong submission.\n4. Highest problems solved + fastest time wins.',
            prizes={'1st': '₹5,000', '2nd': '₹3,000', '3rd': '₹2,000'},
            banner_seed='competitive-programming', extra_img_seed='algorithm',
            participation_type='Individual', max_p=100,
        ),
        make_event(
            title='Cybersecurity CTF', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=TOMORROW, deadline_str=DEADLINE_0, time_str='10:00',
            venue='Networking Lab + Online', reg_fee=0,
            description='Capture The Flag competition with 30+ challenges in web exploitation, cryptography, reverse engineering, forensics, and OSINT. Jeopardy format. 8 hours.',
            rules='1. Teams of 2–3.\n2. Do not attack infrastructure — only designated challenge servers.\n3. Flag sharing between teams = ban.\n4. Writeups encouraged post-event.',
            prizes={'1st': '₹8,000 + CTF Merch', '2nd': '₹5,000', '3rd': '₹2,500'},
            banner_seed='cybersecurity', extra_img_seed='hacking-code',
            participation_type='Team', is_team=True, team_min=2, team_max=3, max_p=150,
        ),

        # +3 days
        make_event(
            title='AI Model Challenge', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='10:00',
            venue='Data Science Lab', reg_fee=0,
            description='Build the best ML/DL model for a given dataset announced on event day. Kaggle-style leaderboard. GPU compute provided for top teams.',
            rules='1. Teams of 1–3.\n2. Dataset revealed at 10:00 AM; submission closes at 4:00 PM.\n3. Pre-trained models may be fine-tuned — disclose in README.\n4. Accuracy + interpretability both judged.',
            prizes={'1st': '₹10,000', '2nd': '₹6,000', '3rd': '₹3,000'},
            banner_seed='machine-learning', extra_img_seed='neural-network',
            participation_type='Team', is_team=True, team_min=1, team_max=3, max_p=90,
        ),
        make_event(
            title='Robotics Combat Arena', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='09:00',
            venue='Mechanical Engineering Workshop', reg_fee=0,
            description='Design, build, and battle your autonomous or RC robot in a sumo-style arena. Weight class: under 3 kg. Bots pre-inspected before competition.',
            rules='1. Bot weight ≤ 3 kg.\n2. No open flame, liquid, or radio jammers.\n3. 3-minute match; highest damage / ring-out wins.\n4. Bring spare parts — no sharing between matches.',
            prizes={'1st': '₹12,000 + Champion Belt', '2nd': '₹7,000', '3rd': '₹4,000'},
            banner_seed='robotics', extra_img_seed='robot-arena',
            participation_type='Team', is_team=True, team_min=2, team_max=5, max_p=80,
        ),
        make_event(
            title='Web Dev Showdown', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=PLUS3, deadline_str=DEADLINE_2, time_str='11:00',
            venue='CS Lab Block — Room 301', reg_fee=0,
            description='Design and build a fully functional web app in 4 hours on a surprise problem statement. Judged on UI/UX, functionality, code quality, and creativity.',
            rules='1. Teams of 1–2.\n2. Any framework/language.\n3. Deploy to Vercel/Netlify for judging.\n4. Copied templates = disqualification.',
            prizes={'1st': '₹6,000', '2nd': '₹4,000', '3rd': '₹2,000'},
            banner_seed='web-development', extra_img_seed='ui-design',
            participation_type='Team', is_team=True, team_min=1, team_max=2, max_p=80,
        ),

        # +4 days
        make_event(
            title='Data Science Olympiad', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='10:00',
            venue='Data Science Lab', reg_fee=0,
            description='Multi-round data science competition: EDA, feature engineering, visualisation, and storytelling with data. A real-world dataset from an industry partner.',
            rules='1. Individual.\n2. Tools: Python / R / Tableau.\n3. 3-hour analysis window.\n4. Present findings in 5-minute pitch.',
            prizes={'1st': '₹8,000', '2nd': '₹5,000', '3rd': '₹2,500'},
            banner_seed='data-science', extra_img_seed='data-visualization',
            participation_type='Individual', max_p=80,
        ),
        make_event(
            title='IoT Innovation Challenge', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='09:00',
            venue='Electronics Lab', reg_fee=0,
            description='Build a working IoT prototype solving a real problem using Arduino / Raspberry Pi / ESP32 and any sensors. Prototype must demo live for judges.',
            rules='1. Teams of 2–4.\n2. Hardware kits available on loan.\n3. 6-hour build window.\n4. Working prototype required — concept-only = no score.',
            prizes={'1st': '₹10,000 + Hardware Kit', '2nd': '₹6,000', '3rd': '₹3,000'},
            banner_seed='iot-electronics', extra_img_seed='arduino',
            participation_type='Team', is_team=True, team_min=2, team_max=4, max_p=80,
        ),
        make_event(
            title='Mobile App Sprint', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='10:00',
            venue='CS Lab — Room 105', reg_fee=0,
            description='Design and ship a mobile app (Android / iOS / Flutter / React Native) solving a problem revealed at the start. 5-hour sprint. APK or TestFlight link submitted.',
            rules='1. Teams of 2–3.\n2. Pre-built UI kits allowed; core logic must be written during sprint.\n3. Judged on idea, UX, and demo quality.\n4. No re-submission of previous projects.',
            prizes={'1st': '₹7,000', '2nd': '₹4,500', '3rd': '₹2,500'},
            banner_seed='mobile-app', extra_img_seed='smartphone-code',
            participation_type='Team', is_team=True, team_min=2, team_max=3, max_p=90,
        ),
        make_event(
            title='Open Source Contribution Sprint', category='Tech',
            spoc_id=tech_id, spoc_name=tech_name, spoc_email=tech_id,
            date_str=PLUS4, deadline_str=DEADLINE_3, time_str='11:00',
            venue='CS Block — Open Lab', reg_fee=0,
            description='Find a good-first-issue on a real open source repository and get it merged. Judged on PR quality, communication with maintainers, and impact.',
            rules='1. Individual.\n2. Choose any public GitHub/GitLab repo (pre-approved list provided).\n3. Submit merged PR URL by 5:00 PM.\n4. Stale / trivial PRs (typo fixes only) not counted.',
            prizes={'1st': '₹5,000 + FOSS T-shirt', '2nd': '₹3,000', '3rd': '₹1,500'},
            banner_seed='open-source', extra_img_seed='github-code',
            participation_type='Individual', max_p=100,
        ),
    ]

    # 3. Insert events into Firestore
    print(f"\nInserting {len(events)} events...")
    for ev in events:
        _, ref = db.collection('events').add(ev)
        print(f"  [{ev['category']:<8}] {ev['title'][:45]:<45}  fee=₹{ev['fees']['regular']}  date={ev['date']}")

    print(f"\n✅ Seeded {len(events)} events across 3 SPOCs.")
    print("\nSPOC Login Credentials:")
    print("-" * 55)
    for s in SPOCS:
        print(f"  {s['category']:<10}  {s['email']}  /  {s['password']}")
    print("-" * 55)
    print("Paid events: Hackathon 2026 (₹500), Cricket T10 (₹200), Fashion Show (₹300)")


if __name__ == '__main__':
    run()
