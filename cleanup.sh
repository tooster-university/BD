psql -c "DROP DATABASE IF EXISTS student" -d postgres -U postgres
psql -c "DROP OWNED BY app; DROP USER IF EXISTS app" -d postgres -U postgres
psql -c "CREATE DATABASE student OWNER init" -d postgres -U postgres