-- Generic WebRTC call offer storage for SOS requests and normal bookings.
CREATE TABLE IF NOT EXISTS webrtc_call_offers (
    id SERIAL PRIMARY KEY,
    entity_type VARCHAR(20) NOT NULL,
    entity_id INTEGER NOT NULL,
    offer JSONB NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_webrtc_call_entity UNIQUE (entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_webrtc_call_entity
    ON webrtc_call_offers(entity_type, entity_id);