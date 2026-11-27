-- Xổ số miền Trung: 14 đài, quay lúc 17:15. Lịch đối chiếu với báo chí (Báo Quốc tế, VTC News) và dữ liệu kết quả thực tế.
INSERT INTO provinces (code, region_code, name, game) VALUES
  ('thua-thien-hue','mt','Thừa Thiên Huế','xs'),
  ('phu-yen','mt','Phú Yên','xs'),
  ('dak-lak','mt','Đắk Lắk','xs'),
  ('quang-nam','mt','Quảng Nam','xs'),
  ('da-nang','mt','Đà Nẵng','xs'),
  ('khanh-hoa','mt','Khánh Hòa','xs'),
  ('binh-dinh','mt','Bình Định','xs'),
  ('quang-tri','mt','Quảng Trị','xs'),
  ('quang-binh','mt','Quảng Bình','xs'),
  ('gia-lai','mt','Gia Lai','xs'),
  ('ninh-thuan','mt','Ninh Thuận','xs'),
  ('quang-ngai','mt','Quảng Ngãi','xs'),
  ('dak-nong','mt','Đắk Nông','xs'),
  ('kon-tum','mt','Kon Tum','xs')
ON CONFLICT (code) DO NOTHING;

-- Huế quay thêm Chủ nhật (dữ liệu ghi nhận từ 08/2025; ngày bắt đầu chính xác cần xác nhận).
INSERT INTO draw_schedules (province_code, iso_weekday, draw_time, valid_from) VALUES
  ('thua-thien-hue',1,'17:15','2000-01-01'),
  ('thua-thien-hue',7,'17:15','2025-08-01'),
  ('phu-yen',1,'17:15','2000-01-01'),
  ('dak-lak',2,'17:15','2000-01-01'),
  ('quang-nam',2,'17:15','2000-01-01'),
  ('da-nang',3,'17:15','2000-01-01'),
  ('da-nang',6,'17:15','2000-01-01'),
  ('khanh-hoa',3,'17:15','2000-01-01'),
  ('khanh-hoa',7,'17:15','2000-01-01'),
  ('binh-dinh',4,'17:15','2000-01-01'),
  ('quang-tri',4,'17:15','2000-01-01'),
  ('quang-binh',4,'17:15','2000-01-01'),
  ('gia-lai',5,'17:15','2000-01-01'),
  ('ninh-thuan',5,'17:15','2000-01-01'),
  ('quang-ngai',6,'17:15','2000-01-01'),
  ('dak-nong',6,'17:15','2000-01-01'),
  ('kon-tum',7,'17:15','2000-01-01');

-- xoso.com.vn có bảng kết quả theo ngày cho cả miền Nam và miền Trung: thêm làm nguồn cho hai miền này.
UPDATE data_sources SET regions = '{mb,mn,mt}', name = 'xoso.com.vn (miền Bắc, Nam, Trung)' WHERE code = 'xoso-com-vn';
