-- Dự báo: tạo trước giờ quay, không sửa, không xóa. Đánh giá được tính sau khi có kết quả.
CREATE TABLE forecasts (
  id            text PRIMARY KEY,                 -- '<draw_id>:<model>'
  draw_id       text NOT NULL REFERENCES lottery_draws(id),
  model         text NOT NULL,
  version       text NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  window_from   date,
  window_to     date,
  window_n      int NOT NULL,
  ranking       jsonb NOT NULL,                   -- ["08","75",...] toàn bộ số, xếp từ cao xuống thấp
  scores        jsonb NOT NULL,                   -- điểm 0-100 tương ứng
  probs         jsonb,                            -- xác suất ước lượng (chỉ mô hình có xác suất)
  params        jsonb NOT NULL DEFAULT '{}',
  UNIQUE (draw_id, model)
);
CREATE INDEX ON forecasts (draw_id);

CREATE FUNCTION forecasts_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Dự báo đã công bố không được sửa hay xóa';
END $$;
CREATE TRIGGER forecasts_no_update BEFORE UPDATE OR DELETE ON forecasts
  FOR EACH ROW EXECUTE FUNCTION forecasts_immutable();

CREATE TABLE forecast_evaluations (
  forecast_id     text PRIMARY KEY REFERENCES forecasts(id),
  draw_version    int NOT NULL,
  evaluated_at    timestamptz NOT NULL DEFAULT now(),
  truth_size      int NOT NULL,                   -- số lượng số khác nhau thực sự về
  hits            jsonb NOT NULL,                 -- {"5": 1, "10": 3, "20": 5} hoặc {"6": 1}
  baseline        jsonb NOT NULL,                 -- số trùng kỳ vọng nếu chọn ngẫu nhiên, cùng khóa K
  brier           double precision,
  brier_uniform   double precision
);
