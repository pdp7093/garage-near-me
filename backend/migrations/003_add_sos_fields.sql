-- Migration: Add Missing SOS Fields
-- Created: May 19, 2026
-- Purpose: Add OTP, estimate, and response tracking fields to sos_requests table

-- Create Estimate Status Type (if PostgreSQL and not exists)
DO $$ BEGIN
    CREATE TYPE estimate_status_enum AS ENUM (
        'not_required',
        'pending',
        'approved',
        'rejected'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add missing columns to sos_requests table
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS estimate_status estimate_status_enum DEFAULT 'not_required';
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS estimate_details JSONB;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS estimate_otp VARCHAR(6);
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS estimate_otp_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS estimate_otp_sent_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS garage_note TEXT;
ALTER TABLE sos_requests ADD COLUMN IF NOT EXISTS responded_at TIMESTAMP WITH TIME ZONE;

-- Create indexes for new columns
CREATE INDEX IF NOT EXISTS idx_sos_estimate_status ON sos_requests(estimate_status);
CREATE INDEX IF NOT EXISTS idx_sos_responded_at ON sos_requests(responded_at);
