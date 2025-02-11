#!/bin/bash

# Database connection details
HOST="10.51.45.221"
PORT="5432"
DATABASE="nextcloud"
USERNAME="operator"
PASSWORD="YOURPASSWORDHERE"

# Generate the SQL query to change table owners to relation-6
QUERY=$(cat <<EOF
SELECT 'ALTER TABLE ' || schemaname || '.' || tablename || ' OWNER TO relation-6;'
FROM pg_tables
WHERE tableowner = 'operator';
EOF
)

# Execute the query and generate the ALTER TABLE statements
ALTER_TABLE_STATEMENTS=$(psql -h "$HOST" -p "$PORT" -d "$DATABASE" -U "$USERNAME" -W -c "$QUERY")

# Execute the ALTER TABLE statements
echo "$ALTER_TABLE_STATEMENTS" | psql -h "$HOST" -p "$PORT" -d "$DATABASE" -U "$USERNAME" -W

echo "Owner change complete."

