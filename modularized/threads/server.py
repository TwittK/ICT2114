# threads/server.py
from web.routes import app

def run_app():
    # app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    app.run(debug=False, use_reloader=False)

