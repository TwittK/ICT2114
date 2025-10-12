import bleach, psycopg2, os
from dotenv import load_dotenv
from flask import (
    session,
    redirect,
    url_for,
    flash,
)
from functools import wraps

# Load environment variables from .env
load_dotenv()
DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432")
}

def check_permission(role_name, action):
  """
  Checks whether a specific role has permission to perform a given action.

  This function queries the database to determine if the provided role is granted
  access to the specified permission/action.

  Parameters:
    role_name (str): The name of the role (e.g., 'admin', 'user').
    action (str): The name of the permission or action to check (e.g., 'delete_user').

  Returns:
    bool: True if the role has the permission, False otherwise.
  """
  conn = psycopg2.connect(**DB_PARAMS)
  cur = conn.cursor()
  cur.execute("""
    SELECT 1
    FROM RolePermission rp
    JOIN Roles r ON rp.role_id = r.id
    JOIN Permission p ON rp.permission_id = p.id
    WHERE r.name = %s AND p.name = %s
    LIMIT 1;
  """, (str(role_name), str(action)))

  granted = cur.fetchone() is not None
  conn.close()
  print(f"[DEBUG] Permission check for role '{role_name}' and action '{action}': {granted}")
  return granted

def validate_and_sanitize_text(text):
  """
  Validates and sanitizes a text input by removing HTML tags, trimming whitespace,
  and enforcing length constraints.

  Parameters:
    text (str): The input text to be validated and cleaned.

  Returns:
    str: The sanitized text string.

  Raises:
    ValueError: If input is not a string or its length is not between 1 and 100 characters.
  """
  # Check if input is a string
  if not isinstance(text, str):
    raise ValueError("Input must be a string")
  
  text = text.strip()
  text = bleach.clean(text, tags=[], strip=True)  # Remove all HTML tags

  # Limit string to a maximum of 100 characters
  if not (1 <= len(text) <= 100):
    raise ValueError("Text length must be between 1 and 100 characters")
  
  return text

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "logged_in" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


def require_permission(permission_name):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "logged_in" not in session:
                flash("You must be logged in to access this page.", "danger")
                return redirect(url_for("index"))

            role_name = session.get("role")
            if not role_name:
                flash("No role assigned to user.", "danger")
                return redirect(url_for("index"))

            has_permission = check_permission(role_name, permission_name)

            if not has_permission:
                flash(f"Permission '{permission_name}' required.", "danger")
                return redirect(url_for("index"))

            return f(*args, **kwargs)

        return decorated_function

    return decorator
