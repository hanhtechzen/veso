-- Tin nhắn liên hệ từ trang công khai (quên mật khẩu, báo sai kết quả, góp ý, hợp tác...).
CREATE TABLE contact_messages (
  id          bigserial PRIMARY KEY,
  created_at  timestamptz NOT NULL DEFAULT now(),
  name        text NOT NULL CHECK (length(name) BETWEEN 1 AND 80),
  email       text NOT NULL CHECK (length(email) BETWEEN 3 AND 254),
  phone       text NOT NULL DEFAULT '' CHECK (length(phone) <= 30),
  topic       text NOT NULL CHECK (topic IN ('quen-mat-khau', 'sai-ket-qua', 'gop-y', 'hop-tac', 'khac')),
  message     text NOT NULL CHECK (length(message) BETWEEN 5 AND 3000),
  page        text NOT NULL DEFAULT '',
  user_id     bigint REFERENCES users(id) ON DELETE SET NULL,
  status      text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'doing', 'done', 'spam')),
  admin_note  text NOT NULL DEFAULT '',
  handled_by  text,
  handled_at  timestamptz
);
CREATE INDEX ON contact_messages (status, created_at DESC);
