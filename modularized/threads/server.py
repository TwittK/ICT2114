# threads/server.py
from web.routes import app
from database import (
    init_database,
    create_default_admin,
    create_default_labs_and_cameras,
    insert_default_roles,
)


def setup_app():
    """Initialise database and defaults without starting Flask."""
    init_database()
    insert_default_roles()
    create_default_admin()
    create_default_labs_and_cameras()
