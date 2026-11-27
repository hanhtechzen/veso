-- Các bộ cào trang web. Mặc định TẮT và CHƯA DUYỆT: chủ dự án tự quyết định bật nguồn nào,
-- sau khi xem điều khoản sử dụng của trang (lệnh: python -m xs247.cli source-enable <mã>).
ALTER TABLE data_sources DROP CONSTRAINT IF EXISTS data_sources_kind_check;
ALTER TABLE data_sources ADD CONSTRAINT data_sources_kind_check
  CHECK (kind IN ('official', 'provider', 'aggregator', 'fixture', 'manual'));

INSERT INTO data_sources (code, name, kind, adapter, config, regions, legal_approved, enabled, rate_limit_ms, priority) VALUES
  ('vietlott-web', 'Vietlott.vn (trang chính thức)', 'official', 'vietlott_655',
   '{"respect_robots": true, "max_pages": 10}', '{vl}', false, false, 10000, 10),
  ('minhngoc-web', 'Minh Ngọc (minhngoc.net)', 'aggregator', 'minhngoc',
   '{"respect_robots": true}', '{mn}', false, false, 5000, 30),
  ('xoso-com-vn', 'xoso.com.vn', 'aggregator', 'xosocomvn',
   '{"respect_robots": true}', '{mb}', false, false, 5000, 30)
ON CONFLICT (code) DO NOTHING;
