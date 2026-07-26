# routes_matchmaker.py — Peer-to-Peer Team Finder & Matchmaker Blueprint
import logging
import random
import json
from flask import Blueprint, render_template, jsonify, request, current_app, session
from utils import login_required

matchmaker_bp = Blueprint('matchmaker', __name__, url_prefix='/participant/matchmaker')
logger = logging.getLogger(__name__)

# Fallback rich static list of potential team partners for matchmaker simulation
MOCK_STUDENTS = [
    {
        'id': 'st_001',
        'name': 'Aarav Mehta',
        'college': 'Sapthagiri College of Engineering',
        'skills': ['Python', 'Flask', 'Machine Learning', 'SQL'],
        'interests': ['AI Hackathon', 'Data Science Showdown'],
        'bio': 'Passionate ML developer looking for front-end designer partner to build a SaaS visual scheduler.',
        'avatar': 'https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?auto=format&fit=crop&w=150&q=80',
        'messages': [
            "Hey! Saw you are looking for backend support. I have 2 years of Flask experience.",
            "I'd love to partner up for the AI Hackathon this weekend."
        ]
    },
    {
        'id': 'st_002',
        'name': 'Sneha Kulkarni',
        'college': 'RV College of Engineering',
        'skills': ['Figma', 'UI/UX Design', 'React', 'Tailwind'],
        'interests': ['Designathon', 'Web Development'],
        'bio': 'UI/UX designer. Love clean glassmorphism layouts and responsive user interfaces. Seeking Python developers.',
        'avatar': 'https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=150&q=80',
        'messages': [
            "Hi there! Your profile looks perfect for our design challenge project.",
            "Let's jump on a quick call to align our ideas."
        ]
    },
    {
        'id': 'st_003',
        'name': 'Vikram Aditya',
        'college': 'PES University',
        'skills': ['Solidity', 'Web3', 'Node.js', 'React'],
        'interests': ['Blockchain Hackathon', 'Fintech Challege'],
        'bio': 'Web3 engineer focused on DeFi tools. Ready to implement smart contracts. Need an UI builder.',
        'avatar': 'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=150&q=80',
        'messages': [
            "Hey buddy! Ready to write some smart contract logic for the app?",
            "Let me know if you want to deploy on the testnet together."
        ]
    },
    {
        'id': 'st_004',
        'name': 'Priyanka Sen',
        'college': 'BMSIT Bangalore',
        'skills': ['Flutter', 'Dart', 'Firebase', 'APIs'],
        'interests': ['App Development', 'IoT Smart Cities'],
        'bio': 'Mobile developer. Built 3 Flutter apps. Looking for hardware programmers for IoT integrations.',
        'avatar': 'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=150&q=80',
        'messages': [
            "Hey, saw you have some background in hardware! Let's connect.",
            "We can build an amazing smart city tracker using Flutter and ESP32."
        ]
    }
]

def _db():
    try:
        import app as app_module
        if hasattr(app_module, 'db') and app_module.db is not None:
            return app_module.db
    except Exception:
        pass
    try:
        from models import db
        return db
    except Exception:
        return None


def _get_student_candidates(current_user_email):
    candidates = []
    seen_emails = set()
    if current_user_email:
        seen_emails.add(current_user_email.lower().strip())

    db_conn = _db()
    if db_conn:
        try:
            from google.cloud.firestore_v1.base_query import FieldFilter
            users = db_conn.collection('users').where(filter=FieldFilter('role', '==', 'Participant')).stream()
            for u in users:
                d = u.to_dict()
                email = str(d.get('email', u.id)).lower().strip()
                if email in seen_emails:
                    continue
                skills = d.get('skills') or ['Python', 'Figma']
                interests = d.get('interests') or ['AI Hackathon']
                bio = d.get('bio') or 'Ready to collaborate and build!'
                avatar = d.get('avatar') or f"https://images.unsplash.com/photo-{1500000000000 + (hash(email) % 999999)}?auto=format&fit=crop&w=150&q=80"
                candidates.append({
                    'id': u.id,
                    'name': d.get('name', 'Solo Student'),
                    'college': d.get('college', 'Sapthagiri College'),
                    'skills': skills,
                    'interests': interests,
                    'bio': bio,
                    'avatar': avatar
                })
                seen_emails.add(email)
        except Exception as e:
            logger.warning("Failed to stream users from DB: %s", e)

    # Merge mock students to ensure we have a robust list
    for peer in MOCK_STUDENTS:
        p_email = peer.get('email', peer['id']).lower().strip()
        if p_email not in seen_emails:
            candidates.append({
                'id': peer['id'],
                'name': peer['name'],
                'college': peer['college'],
                'skills': peer['skills'],
                'interests': peer['interests'],
                'bio': peer['bio'],
                'avatar': peer['avatar']
            })
            seen_emails.add(p_email)

    return candidates


@matchmaker_bp.route('/')
@login_required
def matchmaker_dashboard():
    return render_template('participant/matchmaker.html')


@matchmaker_bp.route('/api/match', methods=['POST'])
@login_required
def get_matches():
    data = request.get_json() or {}
    user_skills = data.get('skills', [])
    user_interests = data.get('interests', [])

    if not user_skills and not user_interests:
        return jsonify({'success': False, 'error': 'Skills or Interests are required'}), 400

    current_email = session.get('user_id')
    candidates = _get_student_candidates(current_email)

    user_skills_clean = [s.strip() for s in user_skills if s.strip()]
    user_interests_clean = [i.strip() for i in user_interests if i.strip()]

    # Try Gemini semantic matching
    try:
        api_key = current_app.config.get('GEMINI_API_KEY', '')
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not configured.")

        from google import genai
        client = genai.Client(api_key=api_key)

        candidates_block = ""
        for idx, c in enumerate(candidates):
            candidates_block += f"Candidate {idx+1} (ID: {c['id']}):\n"
            candidates_block += f"  - Name: {c['name']}\n"
            candidates_block += f"  - Skills: {', '.join(c['skills'])}\n"
            candidates_block += f"  - Interests: {', '.join(c['interests'])}\n"
            candidates_block += f"  - Bio: {c['bio']}\n\n"

        prompt = f"""You are an expert AI matchmaking assistant for the Saptha Event Portal.
Your task is to pair solo students for collaborative team events (like Hackathons, Designathons, Web3, or App Development) by analyzing their complementary skills, interests, and background.

Target Student:
- Skills: {user_skills_clean}
- Interests: {user_interests_clean}

Candidate Solo Students:
{candidates_block}

Instructions:
1. Rank candidates based on how well they complement the Target Student.
   - Complementary Skills: A perfect pairing consists of students with different, complementary skills (e.g. Frontend + Backend, UI/UX Designer + Developer, ML Specialist + Web App Builder). If they have identical skills, they are less complementary.
   - Overlapping Interests/Schedules: They should have matching or highly similar event interests so they are attending/interested in the same contests.
2. For each candidate, calculate a "match_score" (integer between 30 and 99).
3. Provide a clear, one-sentence collaborative reasoning ("match_reason") explaining why this pairing is highly complementary.
4. Return ONLY a JSON object matching this schema (no markdown formatting, no prose):
{{
  "matches": [
    {{
      "id": "<candidate_id>",
      "match_score": <int>,
      "match_reason": "<one sentence explanation>"
    }}
  ]
}}
"""
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        raw = response.text.strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1] if '\n' in raw else raw[3:]
            raw = raw.rsplit('```', 1)[0].strip()

        result = json.loads(raw)
        matches_scores = {m['id']: m for m in result.get('matches', []) if isinstance(m, dict)}

        final_matches = []
        for c in candidates:
            match_data = matches_scores.get(c['id'], {})
            score = match_data.get('match_score', 50)
            reason = match_data.get('match_reason', 'Compatible skill sets and interests.')

            final_matches.append({
                'id': c['id'],
                'name': c['name'],
                'college': c['college'],
                'skills': c['skills'],
                'interests': c['interests'],
                'bio': c['bio'],
                'avatar': c['avatar'],
                'match_score': score,
                'match_reason': reason
            })

        final_matches.sort(key=lambda x: x['match_score'], reverse=True)
        return jsonify({'success': True, 'matches': final_matches})

    except Exception as gemini_err:
        logger.warning("Gemini matchmaking failed, falling back to Jaccard similarity: %s", gemini_err)

        final_matches = []
        user_skills_lower = [s.lower().strip() for s in user_skills_clean]
        user_interests_lower = [i.lower().strip() for i in user_interests_clean]

        for peer in candidates:
            peer_skills_lower = [s.lower().strip() for s in peer['skills']]
            peer_interests_lower = [i.lower().strip() for i in peer['interests']]

            skill_intersection = set(user_skills_lower).intersection(set(peer_skills_lower))
            interest_intersection = set(user_interests_lower).intersection(set(peer_interests_lower))

            matching_score = 0
            if user_interests_lower and peer_interests_lower:
                matching_score += 60 * (len(interest_intersection) / max(len(user_interests_lower), len(peer_interests_lower)))

            all_skills = set(user_skills_lower).union(set(peer_skills_lower))
            if all_skills:
                collaborative_score = 40 * (1 - len(skill_intersection) / len(all_skills))
                matching_score += collaborative_score

            matching_score = round(max(30, min(98, matching_score)))

            final_matches.append({
                'id': peer['id'],
                'name': peer['name'],
                'college': peer['college'],
                'skills': peer['skills'],
                'interests': peer['interests'],
                'bio': peer['bio'],
                'avatar': peer['avatar'],
                'match_score': matching_score,
                'match_reason': 'Matched based on shared fests and collaborative skills.'
            })

        final_matches.sort(key=lambda x: x['match_score'], reverse=True)
        return jsonify({'success': True, 'matches': final_matches})

@matchmaker_bp.route('/api/message', methods=['POST'])
@login_required
def send_match_message():
    data = request.get_json() or {}
    peer_id = data.get('peer_id')
    user_message = data.get('message', '')

    peer = next((p for p in MOCK_STUDENTS if p['id'] == peer_id), None)
    if not peer:
        return jsonify({'success': False, 'error': 'Peer not found'}), 404

    # Simulate smart chatbot response after short duration
    reply_pool = peer['messages']
    response_msg = random.choice(reply_pool) if reply_pool else "Hey! That sounds awesome, let's team up!"

    return jsonify({
        'success': True,
        'reply': response_msg,
        'sender': peer['name']
    })
