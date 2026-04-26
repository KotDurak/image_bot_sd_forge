ALTER TABLE user_preset ADD COLUMN cfg_scale REAL DEFAULT 7.0;
ALTER TABLE user_preset ADD COLUMN sampler TEXT DEFAULT 'DPM++ 2M Karras';