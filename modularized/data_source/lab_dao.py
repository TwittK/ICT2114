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

    def insert_lab(self, lab_name, lab_safety_email):
        """Insert a new lab"""
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO lab (lab_name, lab_safety_email) VALUES (%s, %s)",
                    (lab_name, lab_safety_email),
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

    def update_lab(self, new_lab_name, new_lab_email, lab_id):
        """Update lab details using id"""
        try:
            if not lab_id or not str(lab_id).isdigit():
                raise ValueError(f"Invalid lab_id: {lab_id}")

            lab_id = int(lab_id)  # Convert safely

            with self._get_conn() as conn, conn.cursor() as cursor:
                print("[DEBUG] labid: %s", lab_id)
                cursor.execute(
                    "UPDATE lab SET lab_name = %s, lab_safety_email = %s WHERE labid = %s",
                    (new_lab_name, new_lab_email, lab_id),
                )
                conn.commit()
                return True
        except psycopg2.Error:
            return False
