-- Add is_hidden column to tags table
ALTER TABLE tags ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN DEFAULT false;

-- Update existing tags to have is_hidden = false
UPDATE tags SET is_hidden = false WHERE is_hidden IS NULL;

