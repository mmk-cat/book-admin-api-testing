PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20)  NOT NULL CHECK (role IN ('admin', 'reader')),
    status        VARCHAR(20)  NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
    created_at    TEXT         NOT NULL
);

CREATE TABLE IF NOT EXISTS books (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    isbn       VARCHAR(20)   NOT NULL UNIQUE,
    title      VARCHAR(100)  NOT NULL,
    author     VARCHAR(50)   NOT NULL,
    category   VARCHAR(20)   NOT NULL,
    price      NUMERIC(10,2) NOT NULL CHECK (price >= 0),
    stock      INTEGER       NOT NULL CHECK (stock >= 0),
    status     VARCHAR(20)   NOT NULL DEFAULT 'available'
                             CHECK (status IN ('available', 'borrowed', 'off_shelf')),
    created_at TEXT          NOT NULL,
    updated_at TEXT          NOT NULL
);

CREATE TABLE IF NOT EXISTS borrows (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id     INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    status      VARCHAR(20) NOT NULL DEFAULT 'borrowed'
                            CHECK (status IN ('borrowed', 'returned')),
    borrowed_at TEXT NOT NULL,
    due_at      TEXT NOT NULL,
    returned_at TEXT,
    FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_books_category ON books(category);
CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);
CREATE INDEX IF NOT EXISTS idx_borrows_user ON borrows(user_id);
CREATE INDEX IF NOT EXISTS idx_borrows_book ON borrows(book_id);

CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash VARCHAR(64) PRIMARY KEY,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
