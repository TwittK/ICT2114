import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime


def init_database():
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    # Read and execute the SQL file
    with open('init_db.sql', 'r') as sql_file:
        sql_script = sql_file.read()
        cursor.executescript(sql_script)

    conn.commit()
    conn.close()


def create_user(username, email, password, role='user'):
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    password_hash = generate_password_hash(password)

    try:
        cursor.execute('''
                       INSERT INTO users (username, email, password_hash, role)
                       VALUES (?, ?, ?, ?)
                       ''', (username, email, password_hash, role))

        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def verify_user(email, password):
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    cursor.execute('''
                   SELECT id, email, username, password_hash, role, is_active
                   FROM users
                   WHERE email = ?
                     AND is_active = 1
                   ''', (email,))

    user = cursor.fetchone()
    conn.close()

    if user and check_password_hash(user[3], password):
        return {
            'id': user[0],
            'email': user[1],
            'username': user[2],
            'role': user[4],
        }
    return None


def update_last_login(user_id):
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    cursor.execute('''
                   UPDATE users
                   SET last_login = CURRENT_TIMESTAMP
                   WHERE id = ?
                   ''', (user_id,))

    conn.commit()
    conn.close()


def create_default_admin():
    conn = sqlite3.connect('users.sqlite')
    cursor = conn.cursor()

    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "admin"')
    admin_count = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM users WHERE role = "user"')
    user_count = cursor.fetchone()[0]

    conn.close()

    if admin_count == 0:
        create_user('admin', 'admin@labcomply.com', 'admin123', 'admin')
        print("Default admin user created: admin/admin123")

    if user_count == 0:
        create_user('user', 'user@labcomply.com', 'user123', 'user')
        print("Default user account created: user/user123")
