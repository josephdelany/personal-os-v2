-- REQ-CAP-025/026/034: the private worker must see saved processing events
-- when matching an already consumed result. 0076 granted SELECT but enabled
-- RLS without a service-role read policy, silently hiding idempotency receipts.
-- History contains lifecycle metadata, not media/transcript/location payloads.
CREATE POLICY service_capture_processing_history_read
    ON __CORE__.capture_processing_events
    FOR SELECT TO service_role USING (true);
