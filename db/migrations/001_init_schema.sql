--
-- Файл сгенерирован с помощью SQLiteStudio v3.4.21 в Сб май 16 20:11:27 2026
--
-- Использованная кодировка текста: System
--
PRAGMA foreign_keys = off;
BEGIN TRANSACTION;

-- Таблица: _migrations
CREATE TABLE IF NOT EXISTS _migrations (
    version    TEXT     PRIMARY KEY,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
);


-- Таблица: ad_campaigns
CREATE TABLE IF NOT EXISTS ad_campaigns (
    id          INTEGER  PRIMARY KEY AUTOINCREMENT,
    title       TEXT     NOT NULL,-- "Аниме-магазин 'Кавай'"
    ad_type     TEXT     NOT NULL
                         DEFAULT 'photo',-- 'photo' | 'text'
    content     TEXT     NOT NULL,-- Прямая ссылка на картинку ИЛИ текст
    target_link TEXT     NOT NULL,-- Куда ведёт кнопка (Ozon, VK, TG, сайт)
    btn_text    TEXT     DEFAULT '?? Перейти',-- Надпись на кнопке
    remaining   INTEGER  NOT NULL
                         CHECK (remaining >= 0),-- Остаток купленных показов
    total_sold  INTEGER  DEFAULT 0,-- Для отчётности: сколько было куплено
    is_active   INTEGER  DEFAULT 1,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    shown_count INTEGER  DEFAULT 0
);


-- Таблица: ad_impressions_log
CREATE TABLE IF NOT EXISTS ad_impressions_log (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    ad_id         INTEGER  NOT NULL,
    generation_id INTEGER  NOT NULL,-- ссылка на generation_requests.id
    shown_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (
        ad_id
    )
    REFERENCES ad_campaigns (id),
    FOREIGN KEY (
        generation_id
    )
    REFERENCES generation_requests (id)
);


-- Таблица: external_payments
CREATE TABLE IF NOT EXISTS external_payments (
    id              INTEGER   PRIMARY KEY AUTOINCREMENT,
    transaction_id  TEXT      NOT NULL
                              UNIQUE,-- ID от Platega (храним для сверки)
    user_id         BIGINT    NOT NULL,
    package_key     TEXT      NOT NULL,
    amount          INTEGER   NOT NULL,
    credits_granted INTEGER   DEFAULT 0,
    currency        TEXT      DEFAULT 'RUB',
    status          TEXT      DEFAULT 'pending',-- pending > confirmed / canceled
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- Таблица: generation_requests
CREATE TABLE IF NOT EXISTS generation_requests (
    id                  INTEGER      PRIMARY KEY AUTOINCREMENT,
    user                VARCHAR (20) NOT NULL,-- хранит user_id как строку (для совместимости)
    prompt              TEXT         NOT NULL,
    model_used          TEXT,
    preset_used         VARCHAR (50),
    status              VARCHAR (20) NOT NULL
                                     DEFAULT 'pending',
    error_message       TEXT,
    queue_position      INTEGER,
    generation_time_sec REAL,
    created_at          DATETIME     NOT NULL
                                     DEFAULT CURRENT_TIMESTAMP
);


-- Таблица: star_payments
CREATE TABLE IF NOT EXISTS star_payments (
    id              INTEGER  PRIMARY KEY AUTOINCREMENT,
    user_id         BIGINT   NOT NULL,
    payment_id      TEXT     NOT NULL
                             UNIQUE,-- provider_payment_charge_id из Telegram
    stars_amount    INTEGER  NOT NULL,-- сколько звёзд куплено
    credits_granted INTEGER  NOT NULL,-- сколько генераций начислено
    currency        TEXT     NOT NULL
                             DEFAULT 'XTR',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user_settings (user_id) ON DELETE CASCADE
);


-- Таблица: user_preset
CREATE TABLE IF NOT EXISTS user_preset (
    id                   INTEGER      PRIMARY KEY AUTOINCREMENT,
    user_id              BIGINT       NOT NULL,
    preset_key           VARCHAR (50) NOT NULL,
    name                 VARCHAR (50) NOT NULL,
    prompt_suffix        TEXT         NOT NULL
                                      DEFAULT '',
    negative_suffix      TEXT         NOT NULL
                                      DEFAULT '',
    width                INTEGER      NOT NULL
                                      DEFAULT 512,
    height               INTEGER      NOT NULL
                                      DEFAULT 512,
    steps                INTEGER      NOT NULL
                                      DEFAULT 20,
    is_safe_for_business INTEGER      NOT NULL
                                      DEFAULT 1,
    is_premium           INTEGER      NOT NULL
                                      DEFAULT 0,
    created_at           DATETIME     NOT NULL
                                      DEFAULT CURRENT_TIMESTAMP,
    cfg_scale            REAL         DEFAULT 7.0,
    sampler              TEXT         DEFAULT 'DPM++ 2M Karras',
    scheduler            TEXT         DEFAULT 'Automatic',
    prompt_prefix        TEXT         DEFAULT '',
    FOREIGN KEY (
        user_id
    )
    REFERENCES user_settings (user_id) ON DELETE CASCADE
);


-- Таблица: user_quota
CREATE TABLE IF NOT EXISTS user_quota (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    user_id      BIGINT   NOT NULL,
    is_unlimited INTEGER  NOT NULL
                          DEFAULT 0,
    is_banned    INTEGER  NOT NULL
                          DEFAULT 0,
    free_used    INTEGER  NOT NULL
                          DEFAULT 0,
    free_limit   INTEGER  NOT NULL
                          DEFAULT 0,
    last_reset   DATETIME DEFAULT CURRENT_TIMESTAMP,
    paid_credits INTEGER  NOT NULL
                          DEFAULT 0,
    paid_used    INTEGER  NOT NULL
                          DEFAULT 0,
    FOREIGN KEY (
        user_id
    )
    REFERENCES user_settings (user_id) ON DELETE CASCADE
);


-- Таблица: user_settings
CREATE TABLE IF NOT EXISTS user_settings (
    user_id         INTEGER       PRIMARY KEY,
    username        VARCHAR (100),
    model           TEXT,
    preset          VARCHAR (50),
    requests_count  INTEGER       NOT NULL
                                  DEFAULT 0,
    last_request_at DATETIME,
    created_at      DATETIME      NOT NULL
                                  DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL
                                  DEFAULT CURRENT_TIMESTAMP,
    vae             TEXT,
    lora_string     TEXT
);


COMMIT TRANSACTION;
PRAGMA foreign_keys = on;
