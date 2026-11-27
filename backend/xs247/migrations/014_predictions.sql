-- Sổ dự đoán của thành viên (trang Công cụ): một tài liệu cho mỗi người, gồm dự đoán Power và dự đoán lô ba miền.
CREATE TABLE user_prediction_docs (
  user_id     bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  doc         jsonb NOT NULL DEFAULT '{"entries": {}, "lo": {}}',
  updated_at  timestamptz NOT NULL DEFAULT now()
);
