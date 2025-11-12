-- Migration: Add is_admin column to users table

ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT false NOT NULL;

-- Create index for admin queries
CREATE INDEX IF NOT EXISTS idx_users_is_admin ON users(is_admin);

-- Update existing NULL values to false
UPDATE users SET is_admin = false WHERE is_admin IS NULL;

