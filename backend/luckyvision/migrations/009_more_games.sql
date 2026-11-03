-- Thêm các trò chơi Vietlott (Lotto 5/35, Keno, Max 3D, Max 3D Pro, Bingo18) và xổ số điện toán miền Bắc
-- (1*2*3, Thần Tài 4, 6x36). Mỗi trò chơi là một 'miền' riêng để cơ cấu giải không lẫn nhau.
ALTER TABLE provinces DROP CONSTRAINT IF EXISTS provinces_game_check;
ALTER TABLE provinces ADD CONSTRAINT provinces_game_check CHECK (game IN ('xs', 'power655', 'mega645', 'lotto535', 'keno', 'max3d', 'max3dpro', 'bingo18', 'dt123', 'tt4', 'dt6x36'));
ALTER TABLE lottery_draws DROP CONSTRAINT IF EXISTS lottery_draws_game_check;
ALTER TABLE lottery_draws ADD CONSTRAINT lottery_draws_game_check CHECK (game IN ('xs', 'power655', 'mega645', 'lotto535', 'keno', 'max3d', 'max3dpro', 'bingo18', 'dt123', 'tt4', 'dt6x36'));

INSERT INTO regions (code, name) VALUES
  ('lotto', 'Vietlott Lotto 5/35'),
  ('keno', 'Vietlott Keno'),
  ('max3d', 'Vietlott Max 3D'),
  ('max3dpro', 'Vietlott Max 3D Pro'),
  ('bingo', 'Vietlott Bingo18'),
  ('dt123', 'Xổ số điện toán 1*2*3'),
  ('tt4', 'Xổ số Thần Tài 4'),
  ('dt6x36', 'Xổ số điện toán 6x36')
ON CONFLICT (code) DO NOTHING;
INSERT INTO provinces (code, region_code, name, game) VALUES
  ('lotto535', 'lotto', 'Vietlott Lotto 5/35', 'lotto535'),
  ('keno', 'keno', 'Vietlott Keno', 'keno'),
  ('max3d', 'max3d', 'Vietlott Max 3D', 'max3d'),
  ('max3dpro', 'max3dpro', 'Vietlott Max 3D Pro', 'max3dpro'),
  ('bingo18', 'bingo', 'Vietlott Bingo18', 'bingo18'),
  ('dt123', 'dt123', 'Xổ số điện toán 1*2*3', 'dt123'),
  ('tt4', 'tt4', 'Xổ số Thần Tài 4', 'tt4'),
  ('dt6x36', 'dt6x36', 'Xổ số điện toán 6x36', 'dt6x36')
ON CONFLICT (code) DO NOTHING;

-- Trò chơi Vietlott lấy theo dòng kết quả mới nhất trên vietlott.vn (không cần lập lịch trước). Mặc định tắt.
INSERT INTO data_sources (code, name, kind, adapter, config, regions, legal_approved, enabled, rate_limit_ms, priority) VALUES
  ('vietlott-lotto535', 'Vietlott.vn Lotto 5/35 (trang chính thức)', 'official', 'vietlott_feed', '{"game": "lotto535", "respect_robots": true, "max_pages": 3}', '{lotto}', false, false, 8000, 10),
  ('vietlott-keno', 'Vietlott.vn Keno (trang chính thức)', 'official', 'vietlott_feed', '{"game": "keno", "respect_robots": true, "max_pages": 3}', '{keno}', false, false, 8000, 10),
  ('vietlott-max3d', 'Vietlott.vn Max 3D (trang chính thức)', 'official', 'vietlott_feed', '{"game": "max3d", "respect_robots": true, "max_pages": 3}', '{max3d}', false, false, 8000, 10),
  ('vietlott-max3dpro', 'Vietlott.vn Max 3D Pro (trang chính thức)', 'official', 'vietlott_feed', '{"game": "max3dpro", "respect_robots": true, "max_pages": 3}', '{max3dpro}', false, false, 8000, 10),
  ('vietlott-bingo18', 'Vietlott.vn Bingo18 (trang chính thức)', 'official', 'vietlott_feed', '{"game": "bingo18", "respect_robots": true, "max_pages": 3}', '{bingo}', false, false, 8000, 10)
ON CONFLICT (code) DO NOTHING;

-- Xổ số điện toán miền Bắc: chưa có nguồn tự động được kiểm chứng. Nhập tay trong trang quản trị,
-- hoặc khai báo nguồn http_json của nhà cung cấp dữ liệu (README mục 5).

-- Trò chơi quay nhiều kỳ mỗi ngày: một đài có thể có nhiều kỳ trong ngày, phân biệt bằng số kỳ.
ALTER TABLE lottery_draws DROP CONSTRAINT IF EXISTS lottery_draws_province_code_draw_date_key;
CREATE UNIQUE INDEX IF NOT EXISTS lottery_draws_province_day_seq ON lottery_draws (province_code, draw_date, coalesce(draw_seq, 0))
  WHERE game IN ('lotto535', 'keno', 'bingo18');
CREATE UNIQUE INDEX IF NOT EXISTS lottery_draws_province_day ON lottery_draws (province_code, draw_date)
  WHERE game NOT IN ('lotto535', 'keno', 'bingo18');
