import bleach
import sqlite3

DATABASE = 'users.sqlite'

def check_permission(role_name, action):
  conn = sqlite3.connect(DATABASE)
  cur = conn.cursor()
  cur.execute("""
    SELECT 1
    FROM RolePermission rp
    JOIN Roles r ON rp.role_id = r.id
    JOIN Permission p ON rp.permission_id = p.id
    WHERE r.name = ? AND p.name = ?
    LIMIT 1;
  """, (str(role_name), action))

  granted = cur.fetchone() is not None
  conn.close()
  return granted

def validate_and_sanitize_text(text):

  # Check if input is a string
  if not isinstance(text, str):
    raise ValueError("Input must be a string")
  
  text = text.strip()
  text = bleach.clean(text, tags=[], strip=True)  # Remove all HTML tags

  # Limit string to a maximum of 100 characters
  if not (1 <= len(text) <= 100):
    raise ValueError("Text length must be between 1 and 100 characters")
  
  return text
