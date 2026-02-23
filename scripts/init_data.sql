-- =============================================================================
-- TECHNICAL EXAM: Initial Test Data for Payment Behavior Module
-- This script runs automatically on first PostgreSQL container startup
-- via docker-entrypoint-initdb.d
-- =============================================================================

-- Note: This script creates the 'odoo' database that Odoo will use.
-- Odoo itself will create all tables when it starts.
-- The demo data will be loaded via Odoo's XML demo data mechanism.

-- Create the odoo database if it doesn't exist
SELECT 'CREATE DATABASE odoo OWNER odoo'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'odoo')\gexec
