import sqlite3


class LabDAO:
  def __init__(self, db_path):
    self.db_path = db_path
  
  def get_all_labs(self):
    """Return all labs"""
    from web.routes import dict_factory

    try:
      conn = sqlite3.connect(self.db_path)
      conn.row_factory = dict_factory
      cursor = conn.cursor()
      cursor.execute("SELECT * FROM Lab")

      all_lab_details = cursor.fetchall()
      return all_lab_details
    
    except sqlite3.Error:
      return None
    
    finally:
      conn.close()

  def insert_lab(self, lab_name, lab_safety_email):
    """Insert a new lab"""
    try:
      conn = sqlite3.connect(self.db_path)
      cursor = conn.cursor()
      cursor.execute("INSERT INTO Lab (lab_name, lab_safety_email) VALUES (?, ?)", (lab_name, lab_safety_email))
      conn.commit()

      return True
    
    except sqlite3.Error:
      return False
    
    finally:
      conn.close()

  def delete_lab(self, lab_id):
    """Delete a new lab using id"""
    try:
      conn = sqlite3.connect(self.db_path)
      cursor = conn.cursor()
      cursor.execute("DELETE FROM Lab WHERE LabId = ?", (lab_id,))
      conn.commit()

      return True
    
    except sqlite3.Error:
      return False
    
    finally:
      conn.close()

  def update_lab(self, new_lab_name, new_lab_email, lab_id):
    """Delete a new lab using id"""
    try:
      conn = sqlite3.connect(self.db_path)
      cursor = conn.cursor()
      cursor.execute("UPDATE Lab SET lab_name = ?, lab_safety_email = ? WHERE LabId = ?", (new_lab_name, new_lab_email, lab_id,))
      conn.commit()

      return True
    
    except sqlite3.Error:
      return False
    
    finally:
      conn.close()