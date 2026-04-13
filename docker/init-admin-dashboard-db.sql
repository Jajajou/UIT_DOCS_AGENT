-- Create the admin_dashboard database if it does not already exist.
-- This script runs as the PostgreSQL superuser inside the postgres_uit container.

SELECT 'CREATE DATABASE admin_dashboard'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'admin_dashboard')
\gexec

-- Create a dedicated application user (idempotent).
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'admin_dashboard_app') THEN
        CREATE ROLE admin_dashboard_app WITH LOGIN PASSWORD 'change-me-admin-dashboard-password';
    END IF;
END
$$;

-- Grant privileges.
GRANT ALL PRIVILEGES ON DATABASE admin_dashboard TO admin_dashboard_app;
