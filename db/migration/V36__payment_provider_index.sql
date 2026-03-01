-- Payment provider/status access path for provider-level monitoring and rollout.
ALTER TABLE payment
  ADD INDEX idx_payment_provider_status_created (provider, status, created_at);
