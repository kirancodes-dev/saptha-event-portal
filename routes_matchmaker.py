# routes_matchmaker.py — Peer-to-Peer Team Finder & Matchmaker Blueprint
import logging
import random
from flask import Blueprint, render_template, jsonify, request, current_app
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

@matchmaker_bp.route('/')
@login_required
def matchmaker_dashboard():
    return render_template('participant/matchmaker.html')

@matchmaker_bp.route('/api/match', methods=['POST'])
@login_required
def get_matches():
    data = request.get_json() or {}
    user_skills = [s.lower().strip() for s in data.get('skills', [])]
    user_interests = [i.lower().strip() for i in data.get('interests', [])]

    if not user_skills and not user_interests:
        return jsonify({'success': False, 'error': 'Skills or Interests are required'}), 400

    matches = []
    # Dynamic calculation matching Jaccard coefficient of user interests and skills
    for peer in MOCK_STUDENTS:
        peer_skills = [s.lower() for s in peer['skills']]
        peer_interests = [i.lower() for i in peer['interests']]

        # Compute overlap
        skill_intersection = set(user_skills).intersection(set(peer_skills))
        interest_intersection = set(user_interests).intersection(set(peer_interests))

        # Weight factors: matching interests = 60%, matching skills (complimentary) = 40%
        # Complimentary skills: if peer has skills that user doesn't have, or vice versa (collaboration potential)
        matching_score = 0
        if user_interests and peer_interests:
            matching_score += 60 * (len(interest_intersection) / max(len(user_interests), len(peer_interests)))
        
        # Collaborative skill overlap (ideally they have different skills to complement each other)
        # Give higher score if they have *some* overlap but also unique skills
        all_skills = set(user_skills).union(set(peer_skills))
        if all_skills:
            collaborative_score = 40 * (1 - len(skill_intersection) / len(all_skills))
            matching_score += collaborative_score

        matching_score = round(max(30, min(98, matching_score))) # bound check

        matches.append({
            'id': peer['id'],
            'name': peer['name'],
            'college': peer['college'],
            'skills': peer['skills'],
            'interests': peer['interests'],
            'bio': peer['bio'],
            'avatar': peer['avatar'],
            'match_score': matching_score
        })

    # Sort matches descending
    matches.sort(key=lambda x: x['match_score'], reverse=True)
    return jsonify({'success': True, 'matches': matches})

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
