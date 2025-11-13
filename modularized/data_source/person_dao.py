# Filename: data_source/person_dao.py
import psycopg2

class PersonDAO:
  """
  Data Access Object for person records.

  This class wraps common database operations related to the Person table.
  It is responsible for opening connections (using provided db_params),
  executing queries, and returning structured results.

  Attributes:
      db_params (dict): Keyword arguments passed to psycopg2.connect()
          to establish a database connection (host, port, user, password,
          database, etc.).
  """

  def __init__(self, db_params):
    """Initialise the DAO with database connection parameters.

    Parameters:
        db_params (dict): Parameters forwarded to psycopg2.connect().
    """
    self.db_params = db_params

  def _get_conn(self):
    """Open and return a new database connection.

    Returns:
        connection: A psycopg2 connection.
    """
    return psycopg2.connect(**self.db_params)
  
  def update_last_incompliance(self, id, last_incompliance):
    """
    Update a person's last incompliance date and increment their count.

    Parameters:
        id (int): The PersonId to update.
        last_incompliance (str | datetime): The new incompliance date.

    Returns:
        None
    """
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
    """
    Get the current incompliance count of a person.

    Parameters:
        person_id (int): The PersonId to query.

    Returns:
        int: The current incompliance count for the person.
    """
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
    """
    Insert a new person record into the database.

    Parameters:
        current_date (str | datetime): The initial incompliance date.

    Returns:
        int: The PersonId of the newly inserted person.
    """
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