import os
import psycopg2
from datetime import datetime, timedelta
import requests
from requests.auth import HTTPDigestAuth
import logging
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
DB_PARAMS = {
    "dbname": os.getenv("POSTGRES_DB"),
    "user": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432")
}

class StorageExpiration:
    def __init__(self, db_params, fdid, username, password, nvr_ip):
        self.db_params = db_params
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
            self.conn = psycopg2.connect(**self.db_params)
            self.cursor = self.conn.cursor()
            logging.info("[START] Database connection opened.")

        except psycopg2.Error:
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
            self.cursor.execute(
                """
                SELECT DetectionId, snapshotId, imageURL
                FROM Snapshot
                WHERE time_generated < %s
                """,
                (self.expiration_date,),
            )
            expired_snapshots = self.cursor.fetchall()
            logging.info(f"Found {len(expired_snapshots)} expired snapshot(s).")

            for detection_id, snapshot_id, image_url in expired_snapshots:
                
                # Felete image from face library in NVR
                self.nvr_delete_face(snapshot_id)

                # Delete locally saved images
                if image_url and os.path.exists(os.path.join("web", "static", image_url)):
                    os.remove(os.path.join("web", "static", image_url))
                    logging.info(f"Deleted image: {os.path.join('web', 'static', image_url)}")
                else:
                    logging.warning(f"Image not found: {os.path.join('web', 'static', image_url)}")

                # Delete from snapshot table
                self.cursor.execute("DELETE FROM Snapshot WHERE DetectionId = %s", (detection_id,))
                logging.info(f"Deleted DB record ID: {detection_id}")
                self.conn.commit()

                self.cursor.execute("BEGIN TRANSACTION")
                self.cursor.execute("DELETE FROM Person WHERE last_incompliance < %s", (self.expiration_date,))
                logging.info("Deleted expired entries from Person table.")
                self.conn.commit()

        except psycopg2.Error:
            self.conn.rollback()
            logging.exception("Error deleting expired records, deletion aborted.")

    def close(self):
        self.cursor.close()
        self.conn.close()
        logging.info("[END] Database connection closed.")


expiration_routine = StorageExpiration(DB_PARAMS, "D3FB23C8155040E4BE08374A418ED0CA", "admin", "Sit12345", "192.168.1.63")
expiration_routine.open()
expiration_routine.delete_expired()
expiration_routine.close()
