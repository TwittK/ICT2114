from flask import Flask, render_template, request
import sqlite3
import os

app = Flask(__name__)

DATABASE = "detections.sqlite"
SNAPSHOT_FOLDER = "snapshots"

@app.route("/", methods=["GET", "POST"])
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

if __name__ == "__main__":
    app.run(debug=True)
