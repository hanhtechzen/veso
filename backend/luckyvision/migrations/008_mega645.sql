-- Vietlott Mega 6/45: chọn 6 số từ 01–45, quay thứ Tư, thứ Sáu, Chủ nhật lúc 18:00.
-- Mở rộng danh sách trò chơi hợp lệ (trước đây chỉ có xs và power655).
ALTER TABLE provinces DROP CONSTRAINT IF EXISTS provinces_game_check;
ALTER TABLE provinces ADD CONSTRAINT provinces_game_check CHECK (game IN ('xs', 'power655', 'mega645'));
ALTER TABLE lottery_draws DROP CONSTRAINT IF EXISTS lottery_draws_game_check;
ALTER TABLE lottery_draws ADD CONSTRAINT lottery_draws_game_check CHECK (game IN ('xs', 'power655', 'mega645'));
INSERT INTO regions (code, name) VALUES ('mega', 'Vietlott Mega 6/45') ON CONFLICT (code) DO NOTHING;
INSERT INTO provinces (code, region_code, name, game) VALUES ('mega645', 'mega', 'Vietlott Mega 6/45', 'mega645')
ON CONFLICT (code) DO NOTHING;
INSERT INTO draw_schedules (province_code, iso_weekday, draw_time, valid_from) VALUES
  ('mega645', 3, '18:00', '2016-07-01'), ('mega645', 5, '18:00', '2016-07-01'), ('mega645', 7, '18:00', '2016-07-01');
INSERT INTO prize_structures (region_code, prize_code, name, sort_order, count, digits) VALUES
  ('mega', 'main', 'Bộ số trúng thưởng', 1, 6, 2);
INSERT INTO data_sources (code, name, kind, adapter, config, regions, legal_approved, enabled, rate_limit_ms, priority) VALUES
  ('vietlott-mega', 'Vietlott.vn Mega 6/45 (trang chính thức)', 'official', 'vietlott_645',
   '{"respect_robots": true, "max_pages": 10}', '{mega}', false, false, 10000, 10)
ON CONFLICT (code) DO NOTHING;
