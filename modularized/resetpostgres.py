import os
from dotenv import load_dotenv
import psycopg2

# Load .env file first
load_dotenv()

# Get values from .env
DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")  # fallback to localhost
DB_PORT = os.getenv("POSTGRES_PORT", "5432")       # fallback to 5432

# Connect to PostgreSQL
conn = psycopg2.connect(
    dbname=DB_NAME,
    user=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT
)

cursor = conn.cursor()

# Execute schema
cursor.execute("""
    DROP SCHEMA IF EXISTS public CASCADE;
    CREATE SCHEMA public;
""")


conn.commit()
cursor.close()
conn.close()