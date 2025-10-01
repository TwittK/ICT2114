import psycopg2

class PersonDAO:
  def __init__(self, db_params):
    self.db_params = db_params

  def _get_conn(self):
    """Helper to open a new connection."""
    return psycopg2.connect(**self.db_params)
  
  def update_incompliance(self, current_date, person_id):
    """Increment a person's incompliance count and their last incompliance date."""
    with self._get_conn() as conn:
      with conn.cursor() as cursor:
        update_query = """ 
          UPDATE Person 
          SET last_incompliance = %s, incompliance_count = incompliance_count + 1 
          WHERE PersonId = %s;
        """
        cursor.execute(update_query, (current_date, person_id))
        conn.commit()

  def insert_new_person(self, current_date):
    """Insert new record of a person into the database"""
    with self._get_conn() as conn:
      with conn.cursor() as cursor:
        query = """ 
          INSERT INTO Person (last_incompliance, incompliance_count) 
          VALUES (%s, 1) 
          RETURNING PersonId;
        """
        cursor.execute(query, (current_date,))
        conn.commit()
        
        person_id = cursor.fetchone()[0]
        
    return person_id