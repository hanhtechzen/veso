-- Chống dùng lại mã xác thực hai lớp: lưu bước thời gian của mã đã dùng gần nhất.
ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS totp_last_step bigint NOT NULL DEFAULT 0;
