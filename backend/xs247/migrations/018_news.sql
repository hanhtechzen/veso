-- Tin tức: bài tự sinh từ kết quả đã công bố (kind 'auto') và tin trích từ RSS của báo (kind 'external').
CREATE TABLE IF NOT EXISTS news_feeds (
  code            text PRIMARY KEY,
  name            text NOT NULL,
  url             text NOT NULL,
  enabled         boolean NOT NULL DEFAULT false,
  legal_approved  boolean NOT NULL DEFAULT false,   -- đã duyệt pháp lý (giấy phép dùng lại RSS); chưa duyệt thì không được bật
  include_pattern text,                             -- regex (không phân biệt hoa thường) lọc theo tiêu đề/tóm tắt
  respect_robots  boolean NOT NULL DEFAULT true,
  min_interval_s  integer NOT NULL DEFAULT 900,
  last_fetched_at timestamptz,
  last_ok         timestamptz,
  last_error      text
);

CREATE TABLE IF NOT EXISTS news_articles (
  id           bigserial PRIMARY KEY,
  kind         text NOT NULL CHECK (kind IN ('auto', 'external')),
  topic        text NOT NULL,                       -- region_day | vietlott_draw | weekly_stats | external
  dedupe_key   text NOT NULL UNIQUE,
  slug         text UNIQUE,                         -- NULL với tin ngoài (không có trang chi tiết)
  title        text NOT NULL,
  summary      text NOT NULL DEFAULT '',
  body         jsonb,
  region_code  text,
  draw_ids     text[],
  ref_date     date,
  source_name  text,
  source_url   text,
  feed_code    text REFERENCES news_feeds(code) ON DELETE SET NULL,
  published_at timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now(),
  hidden       boolean NOT NULL DEFAULT false,
  hidden_at    timestamptz
);
CREATE INDEX IF NOT EXISTS news_articles_pub_idx ON news_articles (published_at DESC) WHERE NOT hidden;
CREATE INDEX IF NOT EXISTS news_articles_kind_idx ON news_articles (kind, published_at DESC);

INSERT INTO news_feeds (code, name, url, enabled, legal_approved, include_pattern) VALUES
  ('dantri',         'Báo Dân trí',    'https://dantri.com.vn/rss/kinh-doanh.rss', false, false, '(xổ số|xo so|vé số|vietlott|jackpot|độc đắc)'),
  ('dantri-doisong', 'Báo Dân trí',    'https://dantri.com.vn/rss/doi-song.rss',   false, false, '(xổ số|xo so|vé số|vietlott|jackpot|độc đắc)'),
  ('thanhnien',      'Báo Thanh Niên', 'https://thanhnien.vn/rss/kinh-te.rss',     false, false, '(xổ số|xo so|vé số|vietlott|jackpot|độc đắc)'),
  ('vnexpress',      'Báo VnExpress',  'https://vnexpress.net/rss/tin-moi-nhat.rss', false, false, '(xổ số|xo so|vé số|vietlott|jackpot|độc đắc)'),
  ('tuoitre',        'Báo Tuổi Trẻ',   'https://tuoitre.vn/home.rss',              false, false, '(xổ số|xo so|vé số|vietlott|jackpot|độc đắc)')
ON CONFLICT DO NOTHING;
