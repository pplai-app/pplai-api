-- Add location fields to contacts table
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS meeting_latitude NUMERIC(10, 7);
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS meeting_longitude NUMERIC(10, 7);
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS meeting_location_name VARCHAR(255);

