CREATE INDEX IF NOT EXISTS idx_quota_reset
ON user_quota ((free_limit - free_used))
WHERE is_banned = 0 AND is_unlimited = 0;