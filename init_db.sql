CREATE TABLE IF NOT EXISTS users
(
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      VARCHAR(50) UNIQUE  NOT NULL,
    email         VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT                NOT NULL,
    role          VARCHAR(20) DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at    TIMESTAMP   DEFAULT CURRENT_TIMESTAMP,
    last_login    TIMESTAMP,
    is_active     BOOLEAN     DEFAULT 1
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