import bleach, psycopg2, os
from dotenv import load_dotenv

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
  conn = psycopg2.connect(**DB_PARAMS)
  cur = conn.cursor()
  cur.execute("""
    SELECT 1
    FROM RolePermission rp
    JOIN Roles r ON rp.role_id = r.id
    JOIN Permission p ON rp.permission_id = p.id
    WHERE r.name = %s AND p.name = %s
    LIMIT 1;
  """, (str(role_name), action))

  granted = cur.fetchone() is not None
  conn.close()
  print(f"[DEBUG] Permission check for role '{role_name}' and action '{action}': {granted}")
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
