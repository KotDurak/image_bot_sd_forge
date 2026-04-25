#TODO применить если вырастет нагрузка!!!
-- Индекс для быстрого поиска настроек пользователя
CREATE INDEX IF NOT EXISTS idx_user_settings_user_id
ON user_settings(user_id);

-- Индекс для логов генерации (частые запросы по user + статус)
CREATE INDEX IF NOT EXISTS idx_generation_requests_user_status
ON generation_requests(user, status);

-- Индекс для временных запросов (аналитика, админка)
CREATE INDEX IF NOT EXISTS idx_generation_requests_created_at
ON generation_requests(created_at);

-- Индекс для квот (проверка лимитов)
CREATE INDEX IF NOT EXISTS idx_user_quota_user_id
ON user_quota(user_id);

-- Индекс для пресетов (поиск по пользователю + ключу)
CREATE INDEX IF NOT EXISTS idx_user_preset_user_key
ON user_preset(user_id, preset_key);