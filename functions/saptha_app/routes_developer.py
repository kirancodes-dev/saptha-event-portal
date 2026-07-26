# routes_developer.py — Developer API docs blueprint for SapthaEvent
# Python 3.9 compatible

from flask import Blueprint, render_template

developer_bp = Blueprint('developer', __name__)


@developer_bp.route('/developer/docs')
def api_docs():
    return render_template('developer/api_docs.html')
