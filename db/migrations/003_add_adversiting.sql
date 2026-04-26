CREATE TABLE IF NOT EXISTS ad_campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,                  -- "Аниме-магазин 'Кавай'"
    ad_type TEXT NOT NULL DEFAULT 'photo',-- 'photo' | 'text'
    content TEXT NOT NULL,                -- Прямая ссылка на картинку ИЛИ текст
    target_link TEXT NOT NULL,            -- Куда ведёт кнопка (Ozon, VK, TG, сайт)
    btn_text TEXT DEFAULT '👀 Перейти',   -- Надпись на кнопке
    remaining INTEGER NOT NULL CHECK(remaining >= 0), -- Остаток купленных показов
    is_active INTEGER DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);