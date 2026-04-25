-- Единая схема БД для aiosqlite
-- Запускать ТОЛЬКО при первом создании или через idempotent-скрипт

CREATE TABLE IF NOT EXISTS user_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL UNIQUE,
    username VARCHAR(100),
    model TEXT,
    preset VARCHAR(50),
    requests_count INTEGER NOT NULL DEFAULT 0,
    last_request_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generation_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user VARCHAR(20) NOT NULL,  -- хранит user_id как строку (для совместимости)
    prompt TEXT NOT NULL,
    model_used TEXT,
    preset_used VARCHAR(50),
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message TEXT,
    queue_position INTEGER,
    generation_time_sec REAL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_quota (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL,
    is_unlimited INTEGER NOT NULL DEFAULT 0,
    is_banned INTEGER NOT NULL DEFAULT 0,
    free_used INTEGER NOT NULL DEFAULT 0,
    free_limit INTEGER NOT NULL DEFAULT 0,
    last_reset DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_settings(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS user_preset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL,
    preset_key VARCHAR(50) NOT NULL,
    name VARCHAR(50) NOT NULL,
    prompt_suffix TEXT NOT NULL DEFAULT '',
    negative_suffix TEXT NOT NULL DEFAULT '',
    width INTEGER NOT NULL DEFAULT 512,
    height INTEGER NOT NULL DEFAULT 512,
    steps INTEGER NOT NULL DEFAULT 20,
    is_safe_for_business INTEGER NOT NULL DEFAULT 1,
    is_premium INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_settings(user_id) ON DELETE CASCADE
);

-- Индексы для производительности (особенно важны при async-нагрузке)
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id ON user_settings(user_id);
CREATE INDEX IF NOT EXISTS idx_generation_requests_user_time ON generation_requests(user, created_at);
CREATE INDEX IF NOT EXISTS idx_generation_requests_status ON generation_requests(status);
CREATE INDEX IF NOT EXISTS idx_user_quota_user_id ON user_quota(user_id);
