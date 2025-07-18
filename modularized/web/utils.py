def check_permission(conn, role_name, action):
  cur = conn.cursor()
  cur.execute("""
    SELECT 1
    FROM RolePermission rp
    JOIN Roles r ON rp.role_id = r.id
    JOIN Permission p ON rp.permission_id = p.id
    WHERE r.name = ? AND p.name = ?
    LIMIT 1;
  """, (str(role_name), action))
  return cur.fetchone() is not None