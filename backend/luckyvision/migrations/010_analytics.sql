-- Thống kê truy cập, tôn trọng quyền riêng tư: không cookie, không lưu IP.
-- Khách được nhận diện trong ngày bằng mã băm (muối đổi mỗi ngày rồi bị xóa), không thể truy ngược.
CREATE TABLE page_views_daily (
  day    date NOT NULL,
  path   text NOT NULL,
  views  int  NOT NULL DEFAULT 0,
  PRIMARY KEY (day, path)
);
CREATE TABLE visitors_daily (
  day      date NOT NULL,
  visitor  text NOT NULL,          -- 16 ký tự đầu của sha256(muối trong ngày + IP + trình duyệt)
  device   text NOT NULL,
  pages    int  NOT NULL DEFAULT 1,
  PRIMARY KEY (day, visitor)
);
CREATE TABLE referrers_daily (
  day     date NOT NULL,
  source  text NOT NULL,
  views   int  NOT NULL DEFAULT 0,
  PRIMARY KEY (day, source)
);
