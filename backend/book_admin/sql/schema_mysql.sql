CREATE TABLE IF NOT EXISTS users (
    id            INT PRIMARY KEY AUTO_INCREMENT,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20)  NOT NULL,
    status        VARCHAR(20)  NOT NULL DEFAULT 'active',
    created_at    DATETIME     NOT NULL,
    CONSTRAINT chk_users_role CHECK (role IN ('admin', 'reader')),
    CONSTRAINT chk_users_status CHECK (status IN ('active', 'disabled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS books (
    id         INT PRIMARY KEY AUTO_INCREMENT,
    isbn       VARCHAR(20)   NOT NULL UNIQUE,
    title      VARCHAR(100)  NOT NULL,
    author     VARCHAR(50)   NOT NULL,
    category   VARCHAR(20)   NOT NULL,
    price      DECIMAL(10,2) NOT NULL,
    stock      INT           NOT NULL,
    status     VARCHAR(20)   NOT NULL DEFAULT 'available',
    created_at DATETIME      NOT NULL,
    updated_at DATETIME      NOT NULL,
    CONSTRAINT chk_books_price CHECK (price >= 0),
    CONSTRAINT chk_books_stock CHECK (stock >= 0),
    CONSTRAINT chk_books_status CHECK (status IN ('available', 'borrowed', 'off_shelf')),
    INDEX idx_books_category (category),
    INDEX idx_books_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS borrows (
    id          INT PRIMARY KEY AUTO_INCREMENT,
    book_id     INT         NOT NULL,
    user_id     INT         NOT NULL,
    quantity    INT         NOT NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'borrowed',
    borrowed_at DATETIME    NOT NULL,
    due_at      DATETIME    NOT NULL,
    returned_at DATETIME    NULL,
    CONSTRAINT chk_borrows_quantity CHECK (quantity > 0),
    CONSTRAINT chk_borrows_status CHECK (status IN ('borrowed', 'returned')),
    CONSTRAINT fk_borrows_book FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE RESTRICT,
    CONSTRAINT fk_borrows_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
    INDEX idx_borrows_user (user_id),
    INDEX idx_borrows_book (book_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash VARCHAR(64) PRIMARY KEY,
    expires_at DATETIME    NOT NULL,
    created_at DATETIME    NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
