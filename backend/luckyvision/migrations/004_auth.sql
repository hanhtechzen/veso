-- Tài khoản quản trị: mật khẩu băm scrypt, xác thực hai lớp TOTP, phiên đăng nhập bằng cookie.
CREATE TABLE admin_users (
  id              bigserial PRIMARY KEY,
  username        text NOT NULL UNIQUE CHECK (username ~ '^[a-z0-9._-]{3,40}$'),
  display_name    text NOT NULL,
  role            text NOT NULL CHECK (role IN ('viewer', 'editor', 'admin')),
  password_hash   text NOT NULL,
  must_change_pw  boolean NOT NULL DEFAULT false,
  totp_secret     text,
  totp_enabled    boolean NOT NULL DEFAULT false,
  active          boolean NOT NULL DEFAULT true,
  failed_logins   int NOT NULL DEFAULT 0,
  locked_until    timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  last_login_at   timestamptz
);

CREATE TABLE admin_sessions (
  token_hash   text PRIMARY KEY,                 -- sha256 của token; token gốc chỉ nằm trong cookie
  user_id      bigint NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  ip           text,
  user_agent   text,
  revoked      boolean NOT NULL DEFAULT false
);
CREATE INDEX ON admin_sessions (user_id);
