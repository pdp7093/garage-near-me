-- Add price_type column to garage_services table
ALTER TABLE garage_services 
ADD COLUMN price_type VARCHAR(20) DEFAULT 'fixed';

-- Add comment for documentation
COMMENT ON COLUMN garage_services.price_type IS 'Price type: fixed, starting, estimate, or quote';
