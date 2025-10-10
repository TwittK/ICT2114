import psycopg2

class PersonDAO:
  def __init__(self, db_params):
    self.db_params = db_params

  def _get_conn(self):
    """Helper to open a new connection."""
    return psycopg2.connect(**self.db_params)
  
  def update_last_incompliance(self, id, last_incompliance):
    """Update a person's last incompliance date."""
    update_query = """
                    UPDATE Person
                    SET last_incompliance  = %s,
                        incompliance_count = incompliance_count + 1
                    WHERE PersonId = %s; \
                    """
    with self._get_conn() as conn:
      with conn.cursor() as cursor:
        cursor.execute(update_query, (last_incompliance, id))
        conn.commit()

  def get_incompliance_count(self, person_id):
    """Get the current incompliance count of a person."""
    with self._get_conn() as conn:
      with conn.cursor() as cursor:
        cursor.execute("""
                        SELECT incompliance_count
                        FROM Person
                        WHERE PersonId = %s
                        """, (person_id,))

        updated_count = cursor.fetchone()[0]
        return updated_count
      
  def insert_new_person(self, current_date):
    """Insert new record of a person into the database."""
    query = """
            INSERT INTO Person (last_incompliance, incompliance_count)
            VALUES (%s, 1) RETURNING PersonId; \
            """
    with self._get_conn() as conn:
      with conn.cursor() as cursor:
        cursor.execute(query, (current_date,))
        conn.commit()

        person_id = cursor.fetchone()[0]
        return person_id