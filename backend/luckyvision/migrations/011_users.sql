-- Tài khoản người dùng công khai (tách riêng với tài khoản quản trị), tỉnh và bộ số yêu thích.
CREATE TABLE users (
  id             bigserial PRIMARY KEY,
  email          text NOT NULL UNIQUE CHECK (email = lower(email) AND email LIKE '%_@_%._%'),
  display_name   text NOT NULL CHECK (length(display_name) BETWEEN 1 AND 60),
  password_hash  text NOT NULL,
  failed_logins  int NOT NULL DEFAULT 0,
  locked_until   timestamptz,
  created_at     timestamptz NOT NULL DEFAULT now(),
  last_login_at  timestamptz
);
CREATE TABLE user_sessions (
  token_hash  text PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz NOT NULL,
  revoked     boolean NOT NULL DEFAULT false
);
CREATE INDEX ON user_sessions (user_id);
CREATE TABLE user_fav_provinces (
  user_id        bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  province_code  text NOT NULL REFERENCES provinces(code),
  created_at     timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, province_code)
);
-- kind: lo (các số lô 00–99 theo phạm vi), pick (bộ số Power/Mega), ticket (số vé ba miền theo phạm vi)
CREATE TABLE user_fav_sets (
  id          bigserial PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind        text NOT NULL CHECK (kind IN ('lo', 'pick', 'ticket')),
  scope       text NOT NULL,          -- mb | mn | mt | mã đài | power655 | mega645
  numbers     text[] NOT NULL,
  label       text NOT NULL DEFAULT '',
  created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON user_fav_sets (user_id);
