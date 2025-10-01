import psycopg2
from psycopg2.extras import RealDictCursor


class RoleDAO:
    def __init__(self, db_params):
        self.db_params = db_params

    def _get_conn(self):
        """Helper to return a new connection with dict-style rows."""
        return psycopg2.connect(**self.db_params, cursor_factory=RealDictCursor)

    def get_all_roles(self):
        """Return roles in list of dicts"""
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT * FROM roles")
            return cursor.fetchall()

    def get_all_permissions(self):
        """Return permissions in list of dicts"""
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT * FROM permission")
            return cursor.fetchall()

    def get_all_rolepermissions(self):
        """Return list of tuples (role_id, permission_id)"""
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT * FROM rolepermission")
            rows = cursor.fetchall()
            # rows will be list of dicts (with RealDictCursor)
            return [(row["role_id"], row["permission_id"]) for row in rows]

    def insert_new_role(self, role_name):
        """Creates a new role with no permissions."""
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                cursor.execute("INSERT INTO roles (name) VALUES (%s)", (role_name,))
                conn.commit()
                return True
        except psycopg2.IntegrityError:
            return False

    def delete_role(self, role_name):
        """Deletes a role using its name. Update all affected users' roles to default 'user' role."""
        try:
            with self._get_conn() as conn, conn.cursor() as cursor:
                # Get the ID of the 'user' role (default role)
                cursor.execute("SELECT id FROM Roles WHERE name = %s", ("user",))
                user_role_id = cursor.fetchone()
                if not user_role_id:
                    raise ValueError("Default 'user' role does not exist.")

                # Get the ID of the role we want to delete
                cursor.execute("SELECT id FROM Roles WHERE name = %s", (role_name,))
                role_to_delete = cursor.fetchone()
                if not role_to_delete:
                    raise ValueError(f"Role '{role_name}' not found.")

                # Update users with the role being deleted
                cursor.execute(
                    "UPDATE users SET role = %s WHERE role = %s",
                    (user_role_id[0], role_to_delete[0]),
                )

                # Delete the role
                cursor.execute("DELETE FROM Roles WHERE id = %s", (role_to_delete[0],))
                conn.commit()
                return True
        except psycopg2.IntegrityError:
            return False

    def update_role_permissions(self, permissions_map):
        """
        Transaction to update role to permission mappings.
        permissions_map: set of (role_id, perm_id) tuples
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
        """Returns role ID using role name."""
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
            row = cursor.fetchone()
            return row["id"] if row else None

    def get_permission_id_by_name(self, permission_name):
        """Returns permission ID using permission name."""
        with self._get_conn() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM permission WHERE name = %s", (permission_name,)
            )
            row = cursor.fetchone()
            return row["id"] if row else None
