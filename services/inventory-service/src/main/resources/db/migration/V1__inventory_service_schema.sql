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
    CONSTRAINT uk_inventory_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS book_stock (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    book_id VARCHAR(100) NOT NULL,
    available_quantity INT NOT NULL,
    reserved_quantity INT NOT NULL DEFAULT 0,
    version BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_book_stock_book_id UNIQUE (book_id)
);

CREATE TABLE IF NOT EXISTS inventory_reservation (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    reservation_id VARCHAR(100) NOT NULL,
    checkout_id BIGINT NOT NULL,
    order_id VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    idempotency_key VARCHAR(200) NOT NULL,
    response_payload JSON,
    error_message TEXT,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_inventory_reservation_id UNIQUE (reservation_id),
    CONSTRAINT uk_inventory_reservation_idempotency_key UNIQUE (idempotency_key)
);

CREATE TABLE IF NOT EXISTS inventory_reservation_line (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    reservation_id VARCHAR(100) NOT NULL,
    book_id VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_inventory_reservation_line_id (reservation_id)
);
