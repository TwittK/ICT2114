import os
import sqlite3
from datetime import datetime, timedelta
import requests
from requests.auth import HTTPDigestAuth
import logging

class StorageExpiration:
    def __init__(self, db_path, fdid, username, password, nvr_ip):
        self.db_path = db_path
        self.fdid = fdid
        self.username = username
        self.password = password
        self.nvr_ip = nvr_ip

        logging.basicConfig(
            filename='storage_expiration.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s : %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
    def open(self):
        try:
            # Open connection and calculate expiration threshold (12 months ago)
            self.expiration_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            logging.info("[START] Database connection opened.")

        except sqlite3.Error:
            logging.exception("Error fetching expired snapshots.")

    def nvr_delete_face(self, pid):
        url = f"http://{self.nvr_ip}/ISAPI/Intelligent/FDLib/{self.fdid}/picture/{pid}"
        try:
            response = requests.delete(url, auth=HTTPDigestAuth(self.username, self.password))

            if (response.status_code == 200):
                logging.info(f"Successfully deleted face from NVR: {pid}")
                return True
            
        except Exception as e:
            logging.exception(f"Exception occurred while deleting face from NVR: {pid} ({e})")
            
        logging.error(f"NVR deletion failed for PID {pid}, status code: {response.status_code}")
        return False

    def delete_expired(self):

        try:
            self.cursor.execute("BEGIN TRANSACTION")
            
            # Fetch all incompliance records that are earlier than 12 months ago.
            self.cursor.execute("""SELECT DetectionId, snapshotId, imageURL FROM Snapshot WHERE datetime(time_generated) < datetime(?)""", (self.expiration_date,))
            expired_snapshots = self.cursor.fetchall()
            logging.info(f"Found {len(expired_snapshots)} expired snapshot(s).")

            for detection_id, snapshot_id, image_url in expired_snapshots:
                
                # Felete image from face library in NVR
                self.nvr_delete_face(snapshot_id)

                # Delete locally saved images
                if image_url and os.path.exists(os.path.join("web", "static", image_url)):
                    os.remove(os.path.join("web", "static", image_url))
                    logging.info(f"Deleted image: {os.path.join("web", "static", image_url)}")
                else:
                    logging.warning(f"Image not found: {os.path.join("web", "static", image_url)}")

                # Delete from snapshot table
                self.cursor.execute("DELETE FROM Snapshot WHERE DetectionId = ?", (detection_id,))
                logging.info(f"Deleted DB record ID: {detection_id}")
                self.conn.commit()

                self.cursor.execute("BEGIN TRANSACTION")
                self.cursor.execute("""DELETE FROM Person WHERE datetime(last_incompliance) < datetime(?)""", (self.expiration_date,))
                logging.info("Deleted expired entries from Person table.")
                self.conn.commit()

        except sqlite3.Error:
            self.conn.rollback()
            logging.exception("Error deleting expired records, deletion aborted.")

    def close(self):
        self.cursor.close()
        self.conn.close()
        logging.info("[END] Database connection closed.")


expiration_routine = StorageExpiration('users.sqlite', "D3FB23C8155040E4BE08374A418ED0CA", "admin", "Sit12345", "192.168.1.63")
expiration_routine.open()
expiration_routine.delete_expired()
expiration_routine.close()
