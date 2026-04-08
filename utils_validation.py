"""
utils_validation.py — Input Validation & Sanitization
=====================================================

Provides validation functions for common data types used throughout SapthaEvent.
Prevents invalid data from entering the database.

Usage:
  from utils_validation import validate_email, validate_phone, sanitize_input
  
  if validate_email(email):
      # Process email
  if validate_phone(phone):
      # Process phone
"""

import re
import html
from typing import Tuple, Optional


# =========================================================
# VALIDATION PATTERNS
# =========================================================
EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
PHONE_PATTERN = r'^[0-9]{10}$'  # Indian 10-digit phones
USN_PATTERN = r'^[0-9]{1,2}[A-Z]{2}[0-9]{2}[A-Z]{2}[0-9]{3}$'  # e.g., 1SP26CS001
URL_PATTERN = r'^https?://[^\s/$.?#].[^\s]*$'
NAME_PATTERN = r'^[a-zA-Z\s\'-]{2,100}$'


# =========================================================
# BASIC VALIDATORS
# =========================================================
def validate_email(email: str) -> bool:
    """
    Validate email format.
    
    Args:
        email: Email string to validate
    
    Returns:
        True if valid, False otherwise
    
    Examples:
        validate_email("user@example.com")  # True
        validate_email("invalid.email")     # False
    """
    if not email or not isinstance(email, str):
        return False
    email = email.strip().lower()
    return bool(re.match(EMAIL_PATTERN, email))


def validate_phone(phone: str) -> bool:
    """
    Validate Indian phone number (10 digits).
    
    Args:
        phone: Phone string to validate
    
    Returns:
        True if valid, False otherwise
    
    Examples:
        validate_phone("9876543210")  # True
        validate_phone("98765")       # False
    """
    if not phone or not isinstance(phone, str):
        return False
    phone = phone.strip().replace('-', '').replace(' ', '')
    return bool(re.match(PHONE_PATTERN, phone))


def validate_usn(usn: str) -> bool:
    """
    Validate university student number (Indian format).
    Format: 1SP26CS001, 1SP26EC050, etc.
    
    Args:
        usn: USN string to validate
    
    Returns:
        True if valid, False otherwise
    
    Examples:
        validate_usn("1SP26CS001")  # True
        validate_usn("invalid")     # False
    """
    if not usn or not isinstance(usn, str):
        return False
    usn = usn.strip().upper()
    return bool(re.match(USN_PATTERN, usn))


def validate_name(name: str) -> bool:
    """
    Validate person's name (letters, spaces, hyphens, apostrophes).
    
    Args:
        name: Name string to validate
    
    Returns:
        True if valid, False otherwise
    
    Examples:
        validate_name("John Doe")      # True
        validate_name("Mary O'Brien")  # True
        validate_name("X")             # False (too short)
    """
    if not name or not isinstance(name, str):
        return False
    name = name.strip()
    return bool(re.match(NAME_PATTERN, name))


def validate_url(url: str) -> bool:
    """
    Validate URL format (http/https).
    
    Args:
        url: URL string to validate
    
    Returns:
        True if valid, False otherwise
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return bool(re.match(URL_PATTERN, url))


# =========================================================
# SANITIZATION
# =========================================================
def sanitize_string(text: str, max_length: int = 1000) -> str:
    """
    Sanitize user input string:
    - Strip whitespace
    - HTML escape to prevent XSS
    - Truncate to max length
    
    Args:
        text: Text to sanitize
        max_length: Maximum allowed length
    
    Returns:
        Sanitized string
    
    Examples:
        sanitize_string("<script>alert('xss')</script>")
        # Returns: "&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;"
    """
    if not isinstance(text, str):
        return ""
    
    # Strip whitespace
    text = text.strip()
    
    # HTML escape to prevent XSS
    text = html.escape(text)
    
    # Truncate
    text = text[:max_length]
    
    return text


def sanitize_email(email: str) -> str:
    """
    Sanitize email (lowercase, strip, validate).
    
    Args:
        email: Email to sanitize
    
    Returns:
        Sanitized email or empty string if invalid
    """
    if not isinstance(email, str):
        return ""
    email = email.strip().lower()
    return email if validate_email(email) else ""


def sanitize_phone(phone: str) -> str:
    """
    Sanitize phone (remove dashes, spaces, validate).
    
    Args:
        phone: Phone to sanitize
    
    Returns:
        Sanitized phone (10 digits) or empty string if invalid
    """
    if not isinstance(phone, str):
        return ""
    phone = phone.strip().replace('-', '').replace(' ', '')
    return phone if validate_phone(phone) else ""


# =========================================================
# COMPLEX VALIDATORS
# =========================================================
def validate_registration_data(data: dict) -> Tuple[bool, Optional[str]]:
    """
    Validate complete registration data.
    
    Args:
        data: Registration data dict with keys:
              - lead_name: str
              - lead_email: str
              - lead_phone: str
              - event_id: str
              - team_name: str (optional)
    
    Returns:
        Tuple of (is_valid, error_message)
    
    Examples:
        is_valid, error = validate_registration_data({
            'lead_name': 'John Doe',
            'lead_email': 'john@example.com',
            'lead_phone': '9876543210',
            'event_id': 'EVT-001',
            'team_name': 'Team Alpha'
        })
    """
    if not isinstance(data, dict):
        return False, "Data must be a dictionary"
    
    # Validate required fields
    required_fields = ['lead_name', 'lead_email', 'lead_phone', 'event_id']
    for field in required_fields:
        if not data.get(field):
            return False, f"Missing required field: {field}"
    
    # Validate name
    if not validate_name(data['lead_name']):
        return False, "Invalid name format"
    
    # Validate email
    if not validate_email(data['lead_email']):
        return False, "Invalid email format"
    
    # Validate phone
    if not validate_phone(data['lead_phone']):
        return False, "Invalid phone number (must be 10 digits)"
    
    # Validate team name if provided
    if data.get('team_name') and not isinstance(data['team_name'], str):
        return False, "Invalid team name"
    
    return True, None


def validate_event_data(data: dict) -> Tuple[bool, Optional[str]]:
    """
    Validate complete event data.
    
    Args:
        data: Event data dict with keys:
              - title: str
              - date: str
              - deadline: str
              - venue: str
              - category: str (Technical/Cultural/Sports/Management)
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Data must be a dictionary"
    
    # Validate title
    if not data.get('title') or not isinstance(data['title'], str):
        return False, "Missing or invalid title"
    if len(data['title'].strip()) < 3:
        return False, "Title must be at least 3 characters"
    
    # Validate category
    valid_categories = ['Technical', 'Cultural', 'Sports', 'Management']
    if data.get('category') not in valid_categories:
        return False, f"Category must be one of: {', '.join(valid_categories)}"
    
    # Validate venue
    if not data.get('venue') or not isinstance(data['venue'], str):
        return False, "Missing or invalid venue"
    
    return True, None


# =========================================================
# BATCH SANITIZER
# =========================================================
def sanitize_dict(data: dict, fields_to_sanitize: list = None) -> dict:
    """
    Sanitize multiple fields in a dictionary.
    
    Args:
        data: Dictionary to sanitize
        fields_to_sanitize: List of field names to sanitize.
                           If None, sanitizes all string fields.
    
    Returns:
        Dictionary with sanitized values
    
    Examples:
        data = {
            'name': '<script>alert()</script>',
            'email': 'test@example.com',
            'age': 25
        }
        clean = sanitize_dict(data, ['name', 'email'])
    """
    if not isinstance(data, dict):
        return {}
    
    sanitized = data.copy()
    
    if fields_to_sanitize is None:
        fields_to_sanitize = [k for k, v in data.items() if isinstance(v, str)]
    
    for field in fields_to_sanitize:
        if field in sanitized and isinstance(sanitized[field], str):
            sanitized[field] = sanitize_string(sanitized[field])
    
    return sanitized


if __name__ == '__main__':
    # Test examples
    print("Email validation:")
    print(f"  valid@example.com: {validate_email('valid@example.com')}")
    print(f"  invalid.email: {validate_email('invalid.email')}")
    
    print("\nPhone validation:")
    print(f"  9876543210: {validate_phone('9876543210')}")
    print(f"  98765: {validate_phone('98765')}")
    
    print("\nName validation:")
    print(f"  John Doe: {validate_name('John Doe')}")
    print(f"  X: {validate_name('X')}")
    
    print("\nUSN validation:")
    print(f"  1SP26CS001: {validate_usn('1SP26CS001')}")
    print(f"  invalid: {validate_usn('invalid')}")
    
    print("\nSanitization:")
    print(f"  XSS test: {sanitize_string('<script>alert()</script>')}")
