# routes_gamification.py — Gamification & Leaderboard blueprint
# Python 3.9 compatible

import logging
from flask import Blueprint, render_template, jsonify, session
def _db():
    from app import db
    return db
from utils import login_required

logger = logging.getLogger(__name__)
gamification_bp = Blueprint('gamification', __name__, url_prefix='/gamification')


def award_xp(email: str, amount: int) -> None:
    """Utility to award XP to a student user."""
    if not email or amount <= 0:
        return
    try:
        user_ref = _db().collection('users').document(email)
        user_snap = user_ref.get()
        if user_snap.exists:
            user_data = user_snap.to_dict() or {}
            # Only award XP to Students
            if user_data.get('role') == 'Student':
                current_xp = int(user_data.get('xp', 0) or 0)
                new_xp = current_xp + amount
                user_ref.update({'xp': new_xp})
                logger.info(f"Awarded {amount} XP to student {email}. New XP: {new_xp}")
    except Exception as e:
        logger.error(f"Error awarding XP to {email}: {e}")


@gamification_bp.route('/leaderboard')
@login_required
def leaderboard():
    """Renders the gamification leaderboards (student and department level)."""
    try:
        # Fetch all student users
        users_stream = _db().collection('users').stream()
        students = []
        dept_xp = {}
        dept_student_count = {}

        for doc in users_stream:
            ud = doc.to_dict() or {}
            if ud.get('role') == 'Student':
                xp = int(ud.get('xp', 0) or 0)
                dept = ud.get('department', '').strip() or 'General'
                
                students.append({
                    'name': ud.get('name', 'Anonymous Student'),
                    'email': doc.id,
                    'xp': xp,
                    'department': dept,
                    'college': ud.get('college', 'Unknown College'),
                    'badges': ud.get('badges', [])
                })

                # Calculate department stats
                dept_xp[dept] = dept_xp.get(dept, 0) + xp
                dept_student_count[dept] = dept_student_count.get(dept, 0) + 1

        # Sort students by XP descending
        students.sort(key=lambda x: x['xp'], reverse=True)
        # Add rank
        for i, s in enumerate(students):
            s['rank'] = i + 1

        # Calculate department rankings
        departments = []
        for dept, xp in dept_xp.items():
            count = dept_student_count.get(dept, 1)
            departments.append({
                'name': dept,
                'total_xp': xp,
                'student_count': count,
                'avg_xp': round(xp / count, 1) if count else 0
            })
        
        # Sort departments by total XP descending
        departments.sort(key=lambda x: x['total_xp'], reverse=True)
        for i, d in enumerate(departments):
            d['rank'] = i + 1

        # Top students (first 20)
        top_students = students[:20]

        return render_template(
            'gamification/leaderboard.html',
            top_students=top_students,
            departments=departments,
            current_user_email=session.get('user_id')
        )
    except Exception as e:
        logger.error(f"Error building leaderboard: {e}")
        return render_template('500.html'), 500


@gamification_bp.route('/api/leaderboard')
def api_leaderboard():
    """API endpoint to get leaderboard data as JSON."""
    try:
        users_stream = _db().collection('users').stream()
        students = []
        dept_xp = {}
        dept_student_count = {}

        for doc in users_stream:
            ud = doc.to_dict() or {}
            if ud.get('role') == 'Student':
                xp = int(ud.get('xp', 0) or 0)
                dept = ud.get('department', '').strip() or 'General'
                
                students.append({
                    'name': ud.get('name', 'Anonymous Student'),
                    'email': doc.id,
                    'xp': xp,
                    'department': dept,
                    'college': ud.get('college', 'Unknown College'),
                    'badges': ud.get('badges', [])
                })

                # Calculate department stats
                dept_xp[dept] = dept_xp.get(dept, 0) + xp
                dept_student_count[dept] = dept_student_count.get(dept, 0) + 1

        students.sort(key=lambda x: x['xp'], reverse=True)
        for i, s in enumerate(students):
            s['rank'] = i + 1

        departments = []
        for dept, xp in dept_xp.items():
            count = dept_student_count.get(dept, 1)
            departments.append({
                'name': dept,
                'total_xp': xp,
                'student_count': count,
                'avg_xp': round(xp / count, 1) if count else 0
            })
        departments.sort(key=lambda x: x['total_xp'], reverse=True)
        for i, d in enumerate(departments):
            d['rank'] = i + 1

        return jsonify({
            'status': 'success',
            'students': students[:50],  # Return top 50 in API
            'departments': departments
        })
    except Exception as e:
        logger.error(f"Error in api_leaderboard: {e}")
        return jsonify({'error': str(e)}), 500
