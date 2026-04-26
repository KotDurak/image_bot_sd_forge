-- db/migrations/003_add_paid_quota.sql

-- Добавляем колонки для платных генераций
ALTER TABLE user_quota
ADD COLUMN paid_credits INTEGER NOT NULL DEFAULT 0;

ALTER TABLE user_quota
ADD COLUMN paid_used INTEGER NOT NULL DEFAULT 0;

-- Таблица для истории покупок звёзд (опционально, но полезно для аналитики)
CREATE TABLE IF NOT EXISTS star_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL,
    payment_id TEXT NOT NULL UNIQUE,  -- provider_payment_charge_id из Telegram
    stars_amount INTEGER NOT NULL,     -- сколько звёзд куплено
    credits_granted INTEGER NOT NULL,  -- сколько генераций начислено
    currency TEXT NOT NULL DEFAULT 'XTR',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES user_settings(user_id) ON DELETE CASCADE
);

-- Индексы для быстрых запросов
CREATE INDEX IF NOT EXISTS idx_star_payments_user ON star_payments(user_id);
CREATE INDEX IF NOT EXISTS idx_star_payments_payment_id ON star_payments(payment_id);