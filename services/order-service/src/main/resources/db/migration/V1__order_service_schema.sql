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
    CONSTRAINT uk_order_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id VARCHAR(100) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    checkout_id BIGINT NOT NULL,
    status VARCHAR(50) NOT NULL,
    total_amount DECIMAL(19,4) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_orders_order_id UNIQUE (order_id),
    INDEX idx_orders_checkout_id (checkout_id)
);

CREATE TABLE IF NOT EXISTS order_lines (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id VARCHAR(100) NOT NULL,
    book_id VARCHAR(100) NOT NULL,
    title VARCHAR(500),
    quantity INT NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_order_lines_order_id (order_id)
);
