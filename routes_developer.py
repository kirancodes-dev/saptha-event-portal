# routes_developer.py — Developer API docs blueprint for SapthaEvent
# Python 3.9 compatible

from flask import Blueprint, render_template

developer_bp = Blueprint('developer', __name__)


@developer_bp.route('/developer/docs')
def api_docs():
    return render_template('developer/api_docs.html')


@developer_bp.route('/design-system')
@developer_bp.route('/components-reference')
def design_system():
    return render_template('components_reference.html')
