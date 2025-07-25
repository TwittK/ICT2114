CREATE TABLE IF NOT EXISTS Roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS Permission (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(50) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS RolePermission (
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES Roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES Permission(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS users
(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      VARCHAR(50) UNIQUE  NOT NULL,
    email         VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT                NOT NULL,
    role          TEXT,
    created_at    TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    last_login    TIMESTAMP,
    is_active     BOOLEAN     DEFAULT 1,
    FOREIGN KEY (role) REFERENCES Roles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Lab
(
    LabId            INTEGER PRIMARY KEY AUTOINCREMENT,
    lab_name         TEXT UNIQUE NOT NULL,
    lab_safety_email TEXT        NOT NULL
);

CREATE TABLE IF NOT EXISTS Camera
(
    CameraId           INTEGER PRIMARY KEY AUTOINCREMENT,
    name               VARCHAR(100) NOT NULL,
    resolution         INTEGER      NOT NULL,
    frame_rate         INTEGER      NOT NULL,
    encoding           VARCHAR(50)  NOT NULL,
    camera_ip_type     VARCHAR(50)           DEFAULT 'static' CHECK ( camera_ip_type IN ('static', 'dhcp') ),
    ip_address         VARCHAR(50)  NOT NULL,
    subnet_mask        VARCHAR(50)  NOT NULL,
    gateway            VARCHAR(50)  NOT NULL,
    timezone           VARCHAR(100) NOT NULL,
    sync_with_ntp      INTEGER      NOT NULL DEFAULT 0,
    ntp_server_address VARCHAR(100)          DEFAULT NULL,
    time               DATETIME     NOT NULL,
    camera_user_id     INTEGER      NOT NULL,
    camera_lab_id      INTEGER      NOT NULL,
    FOREIGN KEY (camera_user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (camera_lab_id) REFERENCES Lab (LabId) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS Person
(
    PersonId           INTEGER PRIMARY KEY AUTOINCREMENT,
    last_incompliance  TIMESTAMP NOT NULL,
    incompliance_count INTEGER   NOT NULL
);

CREATE TABLE IF NOT EXISTS Snapshot
(
    DetectionId     INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshotId      TEXT,
    confidence      FLOAT NOT NULL,
    time_generated  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    object_detected TEXT  NOT NULL,
    imageURL        TEXT  NOT NULL,
    person_id       INTEGER,
    camera_id       INTEGER,
    FOREIGN KEY (person_id) REFERENCES Person (PersonId) ON DELETE CASCADE,
    FOREIGN KEY (camera_id) REFERENCES Camera (CameraId) ON DELETE CASCADE
);
