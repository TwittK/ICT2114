import sqlite3
import sqlite_vec
from datetime import datetime
import os

os.makedirs(os.path.join("database"), exist_ok=True)
db = sqlite3.connect(os.path.join("database", "test.sqlite"))
db.execute("PRAGMA foreign_keys = ON;")
db.enable_load_extension(True)
sqlite_vec.load(db)
db.enable_load_extension(False)

sqlite_version, vec_version = db.execute("select sqlite_version(), vec_version()").fetchone()
print(f"sqlite_version={sqlite_version}, vec_version={vec_version}")

db.execute("""
CREATE TABLE Lab (
  LabId INTEGER PRIMARY KEY AUTOINCREMENT,
  lab_name TEXT NOT NULL,
  lab_safety_email TEXT
);
""")

db.execute("""
CREATE TABLE User (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username VARCHAR(50) UNIQUE NOT NULL,
  email VARCHAR(100) UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login TIMESTAMP,
  is_active BOOLEAN DEFAULT 1
);
""")

db.execute("""
CREATE TABLE Camera (
  CameraId INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  resolution TEXT,
  frame_rate INT,
  encoding TEXT
  camera_ip_type TEXT,
  ip_address TEXT NOT NULL,
  subnet_mask TEXT NOT NULL,
  gateway TEXT,
  timezone TEXT,
  sync_with_ntp BOOLEAN DEFAULT 1,
  ntp_server_address TEXT,      
  time TIMESTAMP,
  camera_user_id INT, 
  camera_lab_id INT,   
  FOREIGN KEY (camera_user_id) REFERENCES User(id)               
  FOREIGN KEY (camera_lab_id) REFERENCES Lab(LabId)       
);
""")

db.execute("""
CREATE TABLE Person (
  PersonId INTEGER PRIMARY KEY AUTOINCREMENT,
  last_incompliance TIMESTAMP NOT NULL,
  incompliance_count INTEGER NOT NULL
);
""")


db.execute("""
CREATE TABLE Snapshot (
  DetectionId INTEGER PRIMARY KEY AUTOINCREMENT,
  confidence FLOAT NOT NULL,
  time_generated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  object_detected TEXT NOT NULL,
  imageURL TEXT NOT NULL,
  person_id INTEGER,
  camera_id INTEGER,
  FOREIGN KEY (person_id) REFERENCES Person(id) ON DELETE CASCADE
  FOREIGN KEY (camera_id) REFERENCES Camera(CameraId) ON DELETE CASCADE
);
""")

db.execute("""
CREATE VIRTUAL TABLE Embeddings USING vec0 (
  DetectionId INTEGER,
  embeddings FLOAT[128]
);
""")

# Add admin user
query = """ INSERT INTO User (username, email, password_hash, role, created_at, last_login, is_active)
VALUES (?, ?, ?, ?, ?, ?, ?); """
db.execute(query, 
(
  "admin", 
  "admin@labcomply.com",
  "scrypt:32768:8:1$C9UE7pLeKMPiK8mY$0c1f46701913a4c2135d6b2b02c88700769462f9d202cb8973791da21e1d81da5e6e2930532c4dd52a21655ab0dbec3cd8349eabb7398fcb7f355f90c46dd545",
  "admin",
  datetime.now().isoformat(),
  datetime.now().isoformat(),
  1  
))

# Add normal user
query = """ INSERT INTO User (username, email, password_hash, role, created_at, last_login, is_active)
VALUES (?, ?, ?, ?, ?, ?, ?); """
db.execute(query, 
(
  "user", 
  "user@labcomply.com",
  "scrypt:32768:8:1$KeKDXsrcDyckBmkF$21c660999c9b8456221efbe9f3ebac2215fcb33e9d7a24b969e3a13b1eed453823602e959fb7a4ca79c33a8f40f39f7f6b17cf8f8faf74c79adaf911081a360e",
  "user",
  datetime.now().isoformat(),
  datetime.now().isoformat(),
  1  
))

db.close()


