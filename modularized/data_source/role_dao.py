# Filename: data_source/role_dao.py
import psycopg2
from psycopg2.extras import RealDictCursor


class RoleDAO:
    """
    Data Access Object for role and permission records.

    This class wraps common database operations related to roles,
    permissions, and their mappings. It is responsible for opening
    connections (using provided db_params), executing queries, and
    returning structured results.

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

    def get_all_roles(self):
        """Return all roles as a list of dictionaries.

        Returns:
            list[dict]: List of role records.
        """
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT * FROM roles")
            return cursor.fetchall()

    def get_all_permissions(self):
        """Return all permissions as a list of dictionaries.

        Returns:
            list[dict]: List of permission records.
        """
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT * FROM permission")
            return cursor.fetchall()

    def get_all_rolepermissions(self):
        """Return all role-permission mappings as a list of tuples.

        Returns:
            list[tuple]: List of (role_id, permission_id) tuples.
        """
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT * FROM rolepermission")
            rows = cursor.fetchall()
            return [(row["role_id"], row["permission_id"]) for row in rows]

    def insert_new_role(self, role_name):
        """Create a new role with no permissions.

        Parameters:
            role_name (str): The name of the role to insert.

        Returns:
            bool: True if inserted successfully, False otherwise.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("INSERT INTO roles (name) VALUES (%s)", (role_name,))
                conn.commit()
                return True
        except psycopg2.IntegrityError:
            return False

    def delete_role(self, role_name):
        """Delete a role by its name and update affected users to the default 'user' role.

        Parameters:
            role_name (str): The name of the role to delete.

        Returns:
            bool: True if deleted successfully, False otherwise.
        """
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                # Get the ID of the 'user' role (default role)
                cursor.execute("SELECT id FROM Roles WHERE name = %s", ("user",))
                user_role_id = cursor.fetchone()
                # print(f"[DEBUG] user_role_row: {user_role_id}")  # <-- Add this
                if not user_role_id:
                    raise ValueError("Default 'user' role does not exist.")
                user_role_id = user_role_id["id"]

                # Get the ID of the role we want to delete
                cursor.execute("SELECT id FROM Roles WHERE name = %s", (role_name,))
                role_to_delete = cursor.fetchone()
                # print(f"[DEBUG] role_to_delete: {role_to_delete}")
                if not role_to_delete:
                    raise ValueError(f"Role '{role_name}' not found.")
                role_to_delete = role_to_delete["id"]

                # Update users with the role being deleted
                cursor.execute(
                    "UPDATE users SET role = %s WHERE role = %s",
                    (user_role_id, role_to_delete),
                )

                # Delete the role
                cursor.execute("DELETE FROM Roles WHERE id = %s", (role_to_delete,))
                conn.commit()
                return True
        except psycopg2.IntegrityError:
            return False

    def update_role_permissions(self, permissions_map):
        """
        Transaction to update role to permission mappings.

        Parameters:
            permissions_map (set[tuple]): Set of (role_id, perm_id) tuples.

        Returns:
            None
        """
        with self._get_conn() as conn, conn.cursor() as cursor:
            try:
                cursor.execute("BEGIN;")
                # Clear all permissions first
                cursor.execute("DELETE FROM rolepermission")
                # Insert all new mappings
                for role_id, perm_id in permissions_map:
                    cursor.execute(
                        "INSERT INTO rolepermission (role_id, permission_id) VALUES (%s, %s)",
                        (role_id, perm_id),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def get_role_id_by_name(self, role_name):
        """Return role ID using role name.

        Parameters:
            role_name (str): The name of the role to look up.

        Returns:
            int | None: The role ID if found, else None.
        """
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
            row = cursor.fetchone()
            return row["id"] if row else None

    def get_permission_id_by_name(self, permission_name):
        """Return permission ID using permission name.

        Parameters:
            permission_name (str): The name of the permission to look up.

        Returns:
            int | None: The permission ID if found, else None.
        """
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM permission WHERE name = %s", (permission_name,)
            )
            row = cursor.fetchone()
            return row["id"] if row else None
