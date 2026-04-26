CREATE TABLE IF NOT EXISTS ad_impressions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad_id INTEGER NOT NULL,
    generation_id INTEGER NOT NULL,  -- ссылка на generation_requests.id
    shown_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ad_id) REFERENCES ad_campaigns(id),
    FOREIGN KEY (generation_id) REFERENCES generation_requests(id)
);

CREATE INDEX IF NOT EXISTS idx_ad_gen ON ad_impressions_log(ad_id, generation_id);
CREATE INDEX IF NOT EXISTS idx_shown_at ON ad_impressions_log(shown_at DESC);