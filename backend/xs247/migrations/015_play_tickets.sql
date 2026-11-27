-- Chơi thử: vé thử của thành viên (không phải mua vé thật), tự dò khi kỳ quay có kết quả.
-- draw_id không có khóa ngoại tới lottery_draws vì kỳ quay có thể chưa được lập lịch (lập trước 1 ngày).
CREATE TABLE play_tickets (
  id              bigserial PRIMARY KEY,
  user_id         bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  game            text NOT NULL CHECK (game IN ('xs', 'power655', 'mega645')),
  region_code     text,
  province_code   text,
  draw_date       date NOT NULL,
  draw_id         text NOT NULL,
  numbers         text[] NOT NULL,
  closes_at       timestamptz NOT NULL,
  play_day        date NOT NULL,                  -- ngày Việt Nam lúc tạo vé; dùng đếm hạn mức 10 vé/ngày (tính cả vé đã hủy)
  created_at      timestamptz NOT NULL DEFAULT now(),
  cancelled_at    timestamptz,
  checked_version int,                            -- phiên bản kết quả đã dùng để dò
  result          jsonb                           -- [{"code","name"}]; [] = không trúng; NULL = chưa dò
);
CREATE INDEX play_tickets_user_day ON play_tickets (user_id, play_day);
CREATE INDEX play_tickets_unchecked ON play_tickets (draw_id) WHERE checked_version IS NULL;
