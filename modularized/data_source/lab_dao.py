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

    def insert_lab(self, lab_name, lab_safety_email, lab_safety_telegram):
        """Insert a new lab"""
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO lab (lab_name, lab_safety_email, lab_safety_telegram) VALUES (%s, %s, %s)",
                    (lab_name, lab_safety_email, lab_safety_telegram),
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