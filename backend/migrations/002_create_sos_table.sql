-- Migration: Create SOS (Emergency Breakdown) Table
-- Created: May 19, 2026
-- Purpose: Separate SOS requests from regular bookings

-- Create SOS Status Type (if PostgreSQL)
DO $$ BEGIN
    CREATE TYPE sos_status_enum AS ENUM (
        'broadcasting',
        'accepted',
        'on_the_way',
        'in_progress',
        'completed',
        'cancelled'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Create SOS Requests Table
CREATE TABLE IF NOT EXISTS sos_requests (
    id SERIAL PRIMARY KEY,
    sos_number VARCHAR(50) UNIQUE,
    customer_id INTEGER NOT NULL,
    garage_id INTEGER,
    
    -- Location
    latitude FLOAT NOT NULL,
    longitude FLOAT NOT NULL,
    address VARCHAR(255),
    broadcast_radius_km FLOAT DEFAULT 2.0,
    
    -- Vehicle Info
    vehicle_type VARCHAR(50) NOT NULL,
    vehicle_number VARCHAR(20),
    vehicle_model VARCHAR(100),
    
    -- Problem Description
    description TEXT,
    
    -- Status
    status sos_status_enum DEFAULT 'broadcasting',
    
    -- Pricing
    estimated_charge NUMERIC(10, 2),
    visiting_charge NUMERIC(10, 2),
    final_charge NUMERIC(10, 2),
    platform_commission NUMERIC(10, 2),
    garage_earnings NUMERIC(10, 2),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    accepted_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Foreign Keys
    CONSTRAINT fk_sos_customer FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
    CONSTRAINT fk_sos_garage FOREIGN KEY (garage_id) REFERENCES garages(id) ON DELETE SET NULL
);

-- Create Indexes
CREATE INDEX IF NOT EXISTS idx_sos_customer_id ON sos_requests(customer_id);
CREATE INDEX IF NOT EXISTS idx_sos_garage_id ON sos_requests(garage_id);
CREATE INDEX IF NOT EXISTS idx_sos_status ON sos_requests(status);
CREATE INDEX IF NOT EXISTS idx_sos_sos_number ON sos_requests(sos_number);
CREATE INDEX IF NOT EXISTS idx_sos_created_at ON sos_requests(created_at);
CREATE INDEX IF NOT EXISTS idx_sos_location ON sos_requests(latitude, longitude);
