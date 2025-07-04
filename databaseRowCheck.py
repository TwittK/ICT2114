import sqlite3

conn = sqlite3.connect('users.sqlite')
cursor = conn.cursor()

cursor.execute("SELECT * FROM Camera")
rows = cursor.fetchall()
for row in rows:
    print(row)

conn.close()