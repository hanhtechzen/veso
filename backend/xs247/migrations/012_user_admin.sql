-- Quản trị viên hỗ trợ người dùng quên mật khẩu: đặt lại mật khẩu tạm (bắt đổi), khóa tài khoản.
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_pw boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS disabled boolean NOT NULL DEFAULT false;
