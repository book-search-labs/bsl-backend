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
    CONSTRAINT uk_payment_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS payment_authorization (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    payment_id VARCHAR(100) NOT NULL,
    checkout_id BIGINT NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    amount DECIMAL(19,4) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    status VARCHAR(50) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    pg_transaction_id VARCHAR(200),
    response_payload JSON,
    error_message TEXT,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_payment_authorization_payment_id UNIQUE (payment_id),
    CONSTRAINT uk_payment_authorization_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS payment_cancellation (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    cancellation_id VARCHAR(100) NOT NULL,
    payment_id VARCHAR(100) NOT NULL,
    checkout_id BIGINT NOT NULL,
    status VARCHAR(50) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    response_payload JSON,
    error_message TEXT,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_payment_cancellation_id UNIQUE (cancellation_id),
    CONSTRAINT uk_payment_cancellation_idempotency_key UNIQUE (idempotency_key)
);
