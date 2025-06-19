from flask import Flask, request, session, redirect, url_for, render_template, flash
from functools import wraps
from database import init_database, create_default_admin, verify_user, update_last_login
import sqlite3
import os
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)

DATABASE = "detections.sqlite"
SNAPSHOT_FOLDER = "snapshots"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or session.get('role') != 'admin':
            flash('Admin access required!', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/', methods=["GET", "POST"])
@login_required
def index():
    results = []

    if request.method == "POST":
        date_filter = request.form.get("date")
        object_filter = request.form.get("object_type")

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        query = "SELECT timestamp, object_type, confidence, image_path FROM detections WHERE 1=1"
        params = []

        if date_filter:
            query += " AND DATE(timestamp) = ?"
            params.append(date_filter)

        if object_filter:
            query += " AND object_type = ?"
            params.append(object_filter)

        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()

    return render_template("index.html", results=results, snapshot_folder=SNAPSHOT_FOLDER)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = verify_user(username, password)
        
        if user:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            update_last_login(user['id'])
            
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    return render_template('admin.html')

if __name__ == "__main__":
    init_database()
    create_default_admin()
    app.run(debug=True)
