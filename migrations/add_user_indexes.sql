-- Migration: Add indexes on users table for better query performance
-- Indexes on name, mobile, and whatsapp for faster lookups

-- Index on user name (for searching users by name)
CREATE INDEX IF NOT EXISTS idx_users_name ON users(name);

-- Index on user mobile (for searching users by phone number)
CREATE INDEX IF NOT EXISTS idx_users_mobile ON users(mobile);

-- Index on user whatsapp (for searching users by WhatsApp number)
CREATE INDEX IF NOT EXISTS idx_users_whatsapp ON users(whatsapp);

-- Composite index on (user_id, name) for users table - useful for user-specific name searches
-- Note: This is already covered by the primary key on id, but we add name index separately

-- Verify existing indexes on events and tags user_id
-- Events user_id index should already exist from schema.sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'events' 
        AND indexname = 'idx_events_user_id'
    ) THEN
        CREATE INDEX idx_events_user_id ON events(user_id);
    END IF;
END $$;

-- Tags user_id index should already exist from add_user_id_to_tags.sql migration
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'tags' 
        AND indexname = 'idx_tags_user_id'
    ) THEN
        CREATE INDEX idx_tags_user_id ON tags(user_id);
    END IF;
END $$;

-- Also ensure contacts.user_id is indexed (should already exist from schema.sql)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes 
        WHERE tablename = 'contacts' 
        AND indexname = 'idx_contacts_user_id'
    ) THEN
        CREATE INDEX idx_contacts_user_id ON contacts(user_id);
    END IF;
END $$;

