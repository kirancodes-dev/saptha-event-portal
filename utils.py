from functools import wraps
from flask import session, redirect, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged into the session
        if 'user_id' not in session:
            flash('🔒 Session Expired or Not Logged In. Please log in again.', 'danger')
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def role_required(roles):
    # =========================================================================
    # 🐛 THE BUG HUNTER: 
    # If you accidentally type @role_required instead of @role_required(['Admin']),
    # Flask passes the function itself into 'roles'. This catches that exact typo
    # and tells you exactly which function is broken so you don't have to guess!
    # =========================================================================
    if callable(roles):
        raise SyntaxError(
            f"\n\n🚨 CRITICAL TYPO FOUND! 🚨\n"
            f"You typed '@role_required' without brackets above the function '{roles.__name__}'.\n"
            f"Please go find the 'def {roles.__name__}():' function in your routes files "
            f"and change the decorator to something like @role_required(['Admin'])\n\n"
        )

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user_role = session.get('role')
            
            # If a single string is passed, convert it to a list safely
            if isinstance(roles, str):
                valid_roles = [roles]
            else:
                valid_roles = roles
                
            # Check if the user's role is allowed
            if user_role not in valid_roles:
                flash(f"🛑 Access Denied: You are logged in as '{user_role}', but this page requires {valid_roles}.", "danger")
                return redirect('/login')
                
            return f(*args, **kwargs)
        
        return decorated_function 
    return decorator