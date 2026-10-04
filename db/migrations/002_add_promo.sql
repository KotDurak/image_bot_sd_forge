-- === Миграция 002: Промокоды ===
-- ⚠️ Удаляем старые таблицы, если они были с неправильной структурой
DROP TABLE IF EXISTS user_promo_uses;
DROP TABLE IF EXISTS promo_codes;

-- Таблица промокодов
CREATE TABLE "promo_codes" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
    "code" VARCHAR(50) NOT NULL UNIQUE,
    "bonus_paid_credits" INTEGER NOT NULL DEFAULT 0,
    "bonus_free_limit" INTEGER NOT NULL DEFAULT 0,
    "is_active" INTEGER NOT NULL DEFAULT 1,
    "max_uses" INTEGER DEFAULT NULL,
    "current_uses" INTEGER NOT NULL DEFAULT 0,
    "created_by" BIGINT,
    "created_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY("created_by") REFERENCES "user_settings"("user_id") ON DELETE SET NULL
);

-- Таблица учета использований
CREATE TABLE "user_promo_uses" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
    "user_id" BIGINT NOT NULL,
    "promo_code_id" INTEGER NOT NULL,
    "used_at" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY("user_id") REFERENCES "user_settings"("user_id") ON DELETE CASCADE,
    FOREIGN KEY("promo_code_id") REFERENCES "promo_codes"("id") ON DELETE CASCADE,
    UNIQUE("user_id", "promo_code_id")
);