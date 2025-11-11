#!/bin/bash
set -e

# This script will be executed by the postgres container on startup.
# It reads the POSTGRES_MULTIPLE_DATABASES environment variable, which is a
# comma-separated list of database names, and creates each one.

process_databases() {
    local db_list=$1
    if [ -n "$db_list" ]; then
        echo "Multiple database creation requested: $db_list"
        for db in $(echo $db_list | tr ',' ' '); do
            echo "  Creating database '$db'"
            psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
                CREATE DATABASE "$db";
EOSQL
        done
        echo "Multiple databases created"
    fi
}

# The POSTGRES_DB is created automatically. We only need to create the additional ones.
if [ -n "$POSTGRES_MULTIPLE_DATABASES" ]; then
    # The entrypoint script already creates POSTGRES_DB, so we can filter it out.
    # However, creating it again doesn't cause an error, so this is simpler.
    process_databases "$POSTGRES_MULTIPLE_DATABASES"
fi