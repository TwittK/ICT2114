# threads/server.py
from web.routes import app
from database import (
    init_database,
    create_default_admin,
    create_default_labs,
    insert_default_roles,
)
from shared.camera_discovery import CameraDiscovery
import os

def setup_app():
    """Initialise database and defaults without starting Flask."""
    init_database()
    insert_default_roles()
    create_default_admin()
    create_default_labs()
    
    # Auto discover cameras and add to database using NVR
    cd = CameraDiscovery()
    cd.auto_populate_database()
    
