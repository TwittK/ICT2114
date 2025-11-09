import traceback

import psycopg2
from psycopg2.extras import RealDictCursor


class LabDAO:
    def __init__(self, db_params):
        self.db_params = db_params

    def _get_conn(self):
        """Helper to open a connection with dict-style rows."""
        return psycopg2.connect(**self.db_params, cursor_factory=RealDictCursor)

    def get_all_labs(self):
        """Return all labs as list of dicts"""
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("SELECT * FROM lab")
                all_lab_details = cursor.fetchall()
                return all_lab_details
        except psycopg2.Error:
            return None

    def get_all_labs_safety_email(self):
        """Return all labs as list of dicts"""
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("SELECT * FROM lab JOIN LabSafetyStaff ON lab.LabId = LabSafetyStaff.lab_id")
                all_lab_details = cursor.fetchall()
                return all_lab_details
        except psycopg2.Error:
            return None

    # def insert_lab(self, lab_name, lab_safety_email, lab_safety_telegram):
    #     """Insert a new lab"""
    #     try:
    #         with self._get_conn() as conn, conn.cursor() as cursor:
    #             cursor.execute(
    #                 "INSERT INTO lab (lab_name, lab_safety_email, lab_safety_telegram) VALUES (%s, %s, %s)",
    #                 (lab_name, lab_safety_email, lab_safety_telegram),
    #             )
    #             conn.commit()
    #             return True
    #     except psycopg2.Error:
    #         return False

    def insert_lab(self, lab_name):
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

                # Use the correct key - lowercase 'labid'
                lab_id = row['labid']

                conn.commit()
                return lab_id
        except Exception as e:
            print(f"insert_lab error: {e}")
            import traceback
            traceback.print_exc()
            return None

    def insert_lab_safety_staff(self, lab_id, email, telegram):
        """Insert a new safety staff for a lab"""
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
        """Delete a lab using id"""
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("DELETE FROM lab WHERE labid = %s", (lab_id,))
                conn.commit()
                return True
        except psycopg2.Error:
            return False

    def update_lab(self, new_lab_name, new_lab_email, new_lab_telegram, lab_id):
        """Update lab details using id"""
        try:
            if not lab_id or not str(lab_id).isdigit():
                raise ValueError(f"Invalid lab_id: {lab_id}")

            lab_id = int(lab_id)  # Convert safely

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
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("SELECT * FROM lab WHERE labid = %s", (lab_id,))
                return cursor.fetchone()
        except psycopg2.Error as e:
            print(f"[DB ERROR] Failed to fetch lab by ID: {e}")
            return None

    def update_lab_name(self, lab_id, new_lab_name):
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
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM LabSafetyStaff 
                    WHERE labsafetyid = %s
                    """, (staff_id,), )
                conn.commit()
                # Return True if a row was deleted, False otherwise
                return cursor.rowcount > 0
        except psycopg2.Error as e:
            print(f"Error deleting staff {staff_id}: {e}")
            return False
