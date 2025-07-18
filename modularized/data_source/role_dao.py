import sqlite3

class RoleDAO:
  def __init__(self, db_path):
    self.db_path = db_path
  
  def get_all_roles(self):
    """Return roles in dict"""
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM Roles")
    roles = cursor.fetchall()

    conn.close()
    
    return [r for r in roles]

  def get_all_permissions(self):
    """Return permissions in dict"""
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM Permission")
    permissions = cursor.fetchall()

    conn.close()
    
    return [p for p in permissions]

  def get_all_rolepermissions(self):
    """Return list of tuples (role id, permission id)"""
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM RolePermission")
    role_perms = cursor.fetchall()

    conn.close()
      
    return [tuple(rp) for rp in role_perms]
  
  def insert_new_role(self, role_name):
    """Creates a new role with no permissions."""
    try:
      conn = sqlite3.connect(self.db_path)
      cursor = conn.cursor()
      cursor.execute("INSERT INTO Roles (name) VALUES (?)", (role_name,))
      conn.commit()

      return True

    except sqlite3.IntegrityError:
      return False
    
    finally:
      conn.close()

  def delete_role(self, role_id):
    """Deletes a role using its id."""
    try:
      conn = sqlite3.connect(self.db_path)
      conn.execute("PRAGMA foreign_keys = ON") 
      cursor = conn.cursor()
      cursor.execute("DELETE FROM Roles WHERE id = ?", (role_id,))
      conn.commit()

      return True

    except sqlite3.IntegrityError:
      return False
    
    finally:
      conn.close()
