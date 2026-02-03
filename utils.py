from functools import wraps
from flask import session, flash, redirect, url_for, request

# 1. Login Required Decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please login to access this page.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# 2. Role Required Decorator
def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            
            # Allow single string or list of roles
            roles_list = [allowed_roles] if isinstance(allowed_roles, str) else allowed_roles
            
            if session.get('role') not in roles_list:
                flash("Access Denied: You do not have permission.", "danger")
                # Redirect to their respective dashboards based on their actual role
                role = session.get('role')
                if role == 'Student': return redirect('/participant/dashboard')
                if role == 'ClubSPOC': return redirect('/spoc/dashboard')
                if role == 'Coordinator': return redirect('/event_head/dashboard')
                if role == 'Judge': return redirect('/judge/dashboard')
                return redirect('/')
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator