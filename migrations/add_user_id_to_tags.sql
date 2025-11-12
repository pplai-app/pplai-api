-- Migration: Add user_id to tags table to make tags user-specific
-- System tags will have user_id = NULL
-- Custom tags will have user_id set to the user who created them

-- Add user_id column (nullable for system tags)
ALTER TABLE tags ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;

-- Create index for better query performance
CREATE INDEX IF NOT EXISTS idx_tags_user_id ON tags(user_id);

-- Update existing custom tags to be associated with the first user (if any users exist)
-- This is a fallback - ideally you'd want to handle this more carefully
-- For now, we'll set user_id to NULL for existing tags and they'll be treated as orphaned
-- New tags will be properly associated with users

-- Remove the unique constraint on name (since we now allow same name for different users)
-- First, drop the existing unique constraint if it exists
DO $$ 
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tags_name_key'
    ) THEN
        ALTER TABLE tags DROP CONSTRAINT tags_name_key;
    END IF;
END $$;

-- Add a unique constraint on (name, user_id) for custom tags
-- System tags (user_id IS NULL) can have unique names globally
-- Custom tags (user_id IS NOT NULL) can have same name as system tags but unique per user
CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_name_user_unique 
ON tags(name, COALESCE(user_id, '00000000-0000-0000-0000-000000000000'::uuid))
WHERE is_system_tag = false;

-- Note: System tags should still have unique names globally
-- This is enforced by application logic, not database constraint

