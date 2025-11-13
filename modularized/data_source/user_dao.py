# Filename: data_source/user_dao.py
import psycopg2
from werkzeug.security import generate_password_hash

class UserDAO:
    """
    Data Access Object for user records.

    This class wraps common database operations related to users, roles,
    and permissions. It is responsible for opening connections (using
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

    def get_user_by_id(self, user_id):
        """
        Fetch a user by their ID.

        Parameters:
            user_id (int): The user ID to look up.

        Returns:
            dict | None: Dictionary of user fields if found, else None.
        """
        conn = psycopg2.connect(**self.db_params)

        try:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT id, username, email, role
                           FROM users
                           WHERE id = %s
                           """, (user_id,))
            row = cursor.fetchone()

            if row:
                return {
                    "id": row[0],
                    "username": row[1],
                    "email": row[2],
                    "role": row[3]
                }
            return None
        finally:
            conn.close()

    def get_user_role(self, user_id):
        """
        Return the role name for a user (single role).

        Parameters:
            user_id (int): The user ID to look up.

        Returns:
            str | None: The role name if found, else None.
        """
        conn = psycopg2.connect(**self.db_params)

        try:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT r.name
                           FROM users u
                                    JOIN roles r ON u.role = r.id
                           WHERE u.id = %s
                           """, (user_id,))

            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def get_all_permissions(self):
        """
        Return a list of all permission names.

        Returns:
            list[str]: List of permission names.
        """
        conn = psycopg2.connect(**self.db_params)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM permission ORDER BY id")
            rows = cursor.fetchall()
            return [row[0] for row in rows] if rows else []
        finally:
            conn.close()

    def get_user_permissions(self, user_id):
        """
        Return a list of permission names for the user's role.

        Parameters:
            user_id (int): The user ID to look up.

        Returns:
            list[str]: List of permission names for the user's role.
        """
        conn = psycopg2.connect(**self.db_params)

        try:
            cursor = conn.cursor()
            cursor.execute("""
                           SELECT p.name
                           FROM users u
                                    JOIN roles r ON u.role = r.id
                                    JOIN rolepermission rp ON rp.role_id = r.id
                                    JOIN permission p ON rp.permission_id = p.id
                           WHERE u.id = %s
                           ORDER BY p.name
                           """, (user_id,))
            rows = cursor.fetchall()
            return [row[0] for row in rows] if rows else []
        finally:
            conn.close()

    def update_user(self, user_id, username, email, password=None):
        """
        Update a user's username, email, and optionally password.

        Parameters:
            user_id (int): The user ID to update.
            username (str): The new username.
            email (str): The new email address.
            password (str, optional): The new password (if provided).

        Returns:
            int: Number of rows updated (should be 1 if successful).
        """
        conn = psycopg2.connect(**self.db_params)

        try:
            cursor = conn.cursor()
            if password:
                password_hash = generate_password_hash(password)
                cursor.execute("""
                               UPDATE users
                               SET username=%s,
                                   email=%s,
                                   password_hash=%s
                               WHERE id = %s
                               """, (username, email, password_hash, user_id))
            else:
                cursor.execute("""
                               UPDATE users
                               SET username=%s,
                                   email=%s
                               WHERE id = %s
                               """, (username, email, user_id))

            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()
