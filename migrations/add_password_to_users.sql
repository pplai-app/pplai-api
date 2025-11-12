-- Migration: Add password_hash column to users table for email-based authentication
-- This allows users to sign up and login with email and password

-- Add password_hash column (nullable for existing OAuth users)
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);

-- Note: Existing users created via OAuth will have NULL password_hash
-- Users created via email/password will have a hashed password stored

