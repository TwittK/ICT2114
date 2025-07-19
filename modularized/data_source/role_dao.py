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
    
    return list(roles)

  def get_all_permissions(self):
    """Return permissions in dict"""
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM Permission")
    permissions = cursor.fetchall()

    conn.close()
    
    return list(permissions)

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

  def delete_role(self, role_name):
    """Deletes a role using its name. Update all affected users' roles to default 'user' role. """
    try:
      conn = sqlite3.connect(self.db_path)
      cursor = conn.cursor()
      cursor.execute("UPDATE users SET role = ? WHERE role = ?", ('user', role_name))
      cursor.execute("DELETE FROM Roles WHERE name = ?", (role_name,))
      conn.commit()

      return True

    except sqlite3.IntegrityError:
      return False
    
    finally:
      conn.close()

  def update_role_permissions(self, permissions_map):
    """
    Transaction to update role to permission mappings.
    permissions_map: Dictionary of (role_id, perm_id) tuples
    """
    conn = sqlite3.connect(self.db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
      cursor = conn.cursor()
      cursor.execute("BEGIN TRANSACTION;")

      # Clear all permissions first
      cursor.execute("DELETE FROM RolePermission")

      # Insert all new permissions
      for role_id, perm_id in permissions_map:
        cursor.execute("INSERT INTO RolePermission (role_id, permission_id) VALUES (?, ?)", (role_id, perm_id))

      conn.commit()

    except Exception as e:
      conn.rollback()
      raise e
    
    finally:
      conn.close()
  
  def get_role_id_by_name(self, role_name):
    """Returns role ID using role name."""
    try:
      conn = sqlite3.connect(self.db_path)
      cursor = conn.cursor()
      cursor.execute("SELECT id FROM Roles WHERE name = ?", (role_name,))

      return cursor.fetchone()[0]

    except sqlite3.IntegrityError:
      return None
    
    finally:
      conn.close()

  def get_permission_id_by_name(self, permission_name):
    """Returns permission ID using role name."""
    try:
      conn = sqlite3.connect(self.db_path)
      cursor = conn.cursor()
      cursor.execute("SELECT id FROM Permission WHERE name = ?", (permission_name,))

      return cursor.fetchone()[0]

    except sqlite3.IntegrityError:
      return None
    
    finally:
      conn.close()