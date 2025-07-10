# threads/server.py
from web.routes import app
from database import (
    init_database,
    create_default_admin,
    create_default_labs_and_cameras,
)
import os, secrets


def run_app():
    # app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    init_database()
    create_default_admin()
    create_default_labs_and_cameras()
    app.run(debug=False, use_reloader=False)
