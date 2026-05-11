CREATE TABLE IF NOT EXISTS idempotency_record (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    idempotency_key VARCHAR(200) NOT NULL,
    operation_type VARCHAR(100) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(50) NOT NULL,
    response_payload JSON,
    error_message TEXT,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_refund_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS refund (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    refund_id VARCHAR(100) NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    checkout_id BIGINT NOT NULL,
    user_id VARCHAR(100),
    payment_id VARCHAR(100),
    inventory_reservation_id VARCHAR(100),
    status VARCHAR(50) NOT NULL,
    reason VARCHAR(500) NOT NULL,
    total_amount DECIMAL(19,4) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    request_payload JSON,
    response_payload JSON,
    error_message TEXT,
    version BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_refund_refund_id UNIQUE (refund_id),
    INDEX idx_refund_order_id (order_id),
    INDEX idx_refund_status_updated_at (status, updated_at)
);

CREATE TABLE IF NOT EXISTS refund_item (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    refund_id VARCHAR(100) NOT NULL,
    book_id VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    amount DECIMAL(19,4) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_refund_item_refund_id (refund_id)
);

CREATE TABLE IF NOT EXISTS refund_event (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    refund_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSON NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_refund_event_refund_id (refund_id)
);

CREATE TABLE IF NOT EXISTS outbox_event (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_key VARCHAR(200) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(50) NOT NULL,
    retry_count INT NOT NULL DEFAULT 0,
    next_retry_at DATETIME(6),
    locked_by VARCHAR(100),
    locked_until DATETIME(6),
    error_message TEXT,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    published_at DATETIME(6),
    INDEX idx_refund_outbox_status (status, next_retry_at, id),
    INDEX idx_refund_outbox_aggregate (aggregate_type, aggregate_id)
);
