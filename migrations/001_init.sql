-- 001_init.sql — Initial schema for personal finance tracker

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dt TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    amount_eur REAL,
    exchange_rate REAL,
    category TEXT NOT NULL,
    subcategory TEXT,
    description TEXT,
    receipt_path TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    tags TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tx_dt ON transactions(dt);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_tx_currency ON transactions(currency);
CREATE INDEX IF NOT EXISTS idx_tx_year_month ON transactions(substr(dt, 1, 7));

CREATE TABLE IF NOT EXISTS exchange_rates (
    date TEXT NOT NULL,
    currency TEXT NOT NULL,
    rate_to_eur REAL NOT NULL,
    source TEXT DEFAULT 'api',
    PRIMARY KEY (date, currency)
);

CREATE TABLE IF NOT EXISTS categories (
    name TEXT PRIMARY KEY,
    parent TEXT,
    icon TEXT,
    sort_order INTEGER DEFAULT 0
);

-- Initial categories
INSERT OR IGNORE INTO categories (name, icon, sort_order) VALUES
    ('Еда', '🍽️', 1),
    ('Жильё', '🏠', 2),
    ('Транспорт', '🚗', 3),
    ('Подписки', '📱', 4),
    ('Семья', '👨‍👩‍👧‍👦', 5),
    ('Здоровье', '💊', 6),
    ('Одежда', '👕', 7),
    ('Развлечения', '🎭', 8),
    ('Образование', '📚', 9),
    ('Связь', '📡', 10),
    ('Инфраструктура', '🔧', 11),
    ('Бизнес', '💼', 12),
    ('Прочее', '📌', 13);
