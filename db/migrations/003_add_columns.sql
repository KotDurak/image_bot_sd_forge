-- Добавляем тип промокода и награду для создателя
ALTER TABLE promo_codes ADD COLUMN type VARCHAR(20) NOT NULL DEFAULT 'admin';
ALTER TABLE promo_codes ADD COLUMN reward_paid_credits INTEGER NOT NULL DEFAULT 0;
ALTER TABLE promo_codes ADD COLUMN reward_free_limit INTEGER NOT NULL DEFAULT 0;

-- Добавляем флаг: начислен ли бонус создателю
ALTER TABLE user_promo_uses ADD COLUMN creator_rewarded INTEGER NOT NULL DEFAULT 0;