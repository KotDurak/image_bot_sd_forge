BEGIN TRANSACTION;

-- 1. Создаём правильную таблицу без AUTOINCREMENT
CREATE TABLE user_settings_fixed (
    user_id         INTEGER PRIMARY KEY,
    username        VARCHAR(100),
    model           TEXT,
    preset          VARCHAR(50),
    requests_count  INTEGER NOT NULL DEFAULT 0,
    last_request_at DATETIME,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    vae             TEXT,
    lora_string     TEXT
);

-- 2. Переносим все данные (старый лишний столбец id отбрасываем)
INSERT INTO user_settings_fixed
SELECT user_id, username, model, preset, requests_count, last_request_at,
       created_at, updated_at, vae, lora_string
FROM user_settings;

-- 3. Меняем таблицы местами
DROP TABLE user_settings;
ALTER TABLE user_settings_fixed RENAME TO user_settings;

COMMIT;