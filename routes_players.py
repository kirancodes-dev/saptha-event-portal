"""
routes_players.py — find a player, and a player's profile (UPG-424)

/players finds a player by name among the players of the public sports events;
/players/<code> is the profile. No login. The code comes from the player's
email (services_players.code), which is never shown; nor are the date of birth
(the age is), the phone or the USN.
"""
from flask import Blueprint, abort, render_template, request

from models import db

players_bp = Blueprint('players', __name__, url_prefix='/players')


@players_bp.route('')
def find():
    import services_players
    query = str(request.args.get('q') or '').strip()[:60]
    return render_template('public/players.html', query=query, results=services_players.search(db, query),
                           min_query=services_players.MIN_QUERY)


@players_bp.route('/<code>')
def player(code):
    import services_players
    p = services_players.profile(db, code)
    if p is None:
        abort(404)
    return render_template('public/player_profile.html', p=p)
