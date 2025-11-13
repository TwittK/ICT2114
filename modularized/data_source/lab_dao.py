# Filename: data_source/lab_dao.py
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor


class LabDAO:
    """
    Data Access Object for lab records and safety staff.

    This class wraps common database operations related to labs and
    lab safety staff. It is responsible for opening connections (using
    provided db_params), executing queries, and returning structured results.

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
            connection: A psycopg2 connection configured to return rows as dicts.
        """
        return psycopg2.connect(**self.db_params, cursor_factory=RealDictCursor)

    def get_all_labs(self):
        """Return all labs as a list of dictionaries.

        Returns:
            list[dict] | None: List of lab records, or None on error.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("SELECT * FROM lab")
                all_lab_details = cursor.fetchall()
                return all_lab_details
        except psycopg2.Error:
            return None

    def get_all_labs_safety_email(self):
        """Return all labs joined with safety staff as a list of dictionaries.

        Returns:
            list[dict] | None: List of lab records joined with safety staff, or None on error.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("SELECT * FROM lab JOIN LabSafetyStaff ON lab.LabId = LabSafetyStaff.lab_id")
                all_lab_details = cursor.fetchall()
                return all_lab_details
        except psycopg2.Error:
            return None

    def insert_lab(self, lab_name):
        """Insert a new lab with the given name.

        Parameters:
            lab_name (str): The name of the lab to insert.

        Returns:
            int | None: The LabId of the newly inserted lab, or None on error.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    'INSERT INTO lab (lab_name) VALUES (%s) RETURNING labid',
                    (lab_name,),
                )
                row = cursor.fetchone()
                print(f"DEBUG: Row fetched from insert: {row!r}")

                if row is None:
                    print("No row returned from insert query.")
                    return None

                lab_id = row['labid']

                conn.commit()
                return lab_id
        except Exception as e:
            print(f"insert_lab error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def insert_lab_safety_staff(self, lab_id, email, telegram):
        """Insert a new safety staff member for a lab.

        Parameters:
            lab_id (int): The LabId to associate the staff with.
            email (str): The safety staff's email address.
            telegram (str): The safety staff's Telegram username.

        Returns:
            bool: True if inserted successfully, False otherwise.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO LabSafetyStaff
                    (lab_safety_email, lab_safety_telegram, lab_id) 
                    VALUES (%s, %s, %s)
                    """,
                    (email, telegram, lab_id),
                )
                conn.commit()
                return True
        except psycopg2.Error:
            return False

    def delete_lab(self, lab_id):
        """Delete a lab by its LabId.

        Parameters:
            lab_id (int): The LabId of the lab to delete.

        Returns:
            bool: True if deleted successfully, False otherwise.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("DELETE FROM lab WHERE labid = %s", (lab_id,))
                conn.commit()
                return True
        except psycopg2.Error:
            return False

    def update_lab(self, new_lab_name, new_lab_email, new_lab_telegram, lab_id):
        """Update lab details by LabId.

        Parameters:
            new_lab_name (str): New name for the lab.
            new_lab_email (str): New safety email for the lab.
            new_lab_telegram (str): New safety Telegram username for the lab.
            lab_id (int): The LabId of the lab to update.

        Returns:
            bool: True if updated successfully, False otherwise.
        """
        try:
            if not lab_id or not str(lab_id).isdigit():
                raise ValueError(f"Invalid lab_id: {lab_id}")

            lab_id = int(lab_id)

            with self._get_conn() as conn, conn.cursor() as cursor:
                print("[DEBUG] labid: %s", lab_id)
                cursor.execute(
                    "UPDATE lab SET lab_name = %s, lab_safety_email = %s, lab_safety_telegram = %s WHERE labid = %s",
                    (new_lab_name, new_lab_email, new_lab_telegram, lab_id),
                )
                conn.commit()
                return True
        except psycopg2.Error:
            return False

    def update_lab_telegram(self, lab_id, telegram_username):
        """Update the Telegram username for a lab's safety contact.

        Parameters:
            lab_id (int): The LabId of the lab to update.
            telegram_username (str): The new Telegram username.

        Returns:
            bool: True if updated successfully, False otherwise.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE lab SET lab_safety_telegram = %s WHERE labid = %s",
                    (telegram_username, lab_id),
                )
                conn.commit()
                return True
        except psycopg2.Error as e:
            print(f"[ERROR] DB update failed: {e}")
            return False

    def get_lab_by_id(self, lab_id):
        """Fetch a lab record by its LabId.

        Parameters:
            lab_id (int): The LabId to fetch.

        Returns:
            dict | None: The lab record as a dictionary, or None on error.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("SELECT * FROM lab WHERE labid = %s", (lab_id,))
                return cursor.fetchone()
        except psycopg2.Error as e:
            print(f"[DB ERROR] Failed to fetch lab by ID: {e}")
            return None

    def update_lab_name(self, lab_id, new_lab_name):
        """Update the name of a lab by its LabId.

        Parameters:
            lab_id (int): The LabId of the lab to update.
            new_lab_name (str): The new name for the lab.

        Returns:
            bool: True if updated successfully, False otherwise.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE lab SET lab_name = %s WHERE labid = %s",
                    (new_lab_name, lab_id)
                )
                conn.commit()
                return True
        except psycopg2.Error as e:
            print(f"Error updating lab name: {e}")
            return False

    def update_lab_safety_staff(self, staff_id, email, telegram):
        """Update safety staff details by staff ID.

        Parameters:
            staff_id (int): The LabSafetyStaff ID to update.
            email (str): The new email address.
            telegram (str): The new Telegram username.

        Returns:
            bool: True if updated successfully, False otherwise.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE LabSafetyStaff
                    SET lab_safety_email = %s, lab_safety_telegram = %s
                    WHERE labsafetyid = %s
                    """,
                    (email, telegram, staff_id),
                )
                conn.commit()
                return True
        except psycopg2.Error as e:
            print(f"Error updating staff {staff_id}: {e}")
            return False

    def delete_lab_safety_staff(self, staff_id):
        """Delete a safety staff member by their staff ID.

        Parameters:
            staff_id (int): The LabSafetyStaff ID to delete.

        Returns:
            bool: True if deleted successfully, False otherwise.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM LabSafetyStaff 
                    WHERE labsafetyid = %s
                    """, (staff_id,), )
                conn.commit()
                return cursor.rowcount > 0
        except psycopg2.Error as e:
            print(f"Error deleting staff {staff_id}: {e}")
            return False
