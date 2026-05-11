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
    CONSTRAINT uk_shipment_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS shipment_request (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    shipment_id VARCHAR(100) NOT NULL,
    checkout_id BIGINT NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    address TEXT NOT NULL,
    response_payload JSON,
    error_message TEXT,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_shipment_request_id UNIQUE (shipment_id),
    CONSTRAINT uk_shipment_request_idempotency_key UNIQUE (idempotency_key)
);
