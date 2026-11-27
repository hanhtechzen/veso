-- XS247: lược đồ dữ liệu (mục 5 tài liệu thiết kế)

CREATE TABLE regions (
  code  text PRIMARY KEY,               -- mb, mn, mt, vl (Vietlott)
  name  text NOT NULL
);

CREATE TABLE provinces (
  code         text PRIMARY KEY,        -- tp-hcm, vung-tau, mb, power655 ...
  region_code  text NOT NULL REFERENCES regions(code),
  name         text NOT NULL,
  game         text NOT NULL DEFAULT 'xs' CHECK (game IN ('xs', 'power655')),
  active       boolean NOT NULL DEFAULT true
);

CREATE TABLE draw_schedules (
  id             bigserial PRIMARY KEY,
  province_code  text NOT NULL REFERENCES provinces(code),
  iso_weekday    smallint NOT NULL CHECK (iso_weekday BETWEEN 1 AND 7),   -- 1 = thứ Hai, 7 = Chủ nhật
  draw_time      time NOT NULL,                                          -- giờ Việt Nam
  valid_from     date NOT NULL DEFAULT '2000-01-01',
  valid_to       date
);
CREATE INDEX ON draw_schedules (iso_weekday);

CREATE TABLE draw_holidays (
  id           bigserial PRIMARY KEY,
  region_code  text NOT NULL REFERENCES regions(code),
  date_from    date NOT NULL,
  date_to      date NOT NULL,
  note         text
);

CREATE TABLE prize_structures (
  region_code  text NOT NULL REFERENCES regions(code),
  prize_code   text NOT NULL,           -- db, g1..g8; Vietlott: main, special
  name         text NOT NULL,
  sort_order   smallint NOT NULL,       -- thứ tự hiển thị
  count        smallint NOT NULL,
  digits       smallint NOT NULL,
  valid_from   date NOT NULL DEFAULT '2000-01-01',
  PRIMARY KEY (region_code, prize_code, valid_from)
);

CREATE TABLE data_sources (
  code            text PRIMARY KEY,
  name            text NOT NULL,
  kind            text NOT NULL CHECK (kind IN ('official', 'provider', 'fixture', 'manual')),
  adapter         text NOT NULL,        -- fixture | http_json | manual
  config          jsonb NOT NULL DEFAULT '{}',
  regions         text[] NOT NULL DEFAULT '{}',   -- rỗng = mọi miền
  legal_approved  boolean NOT NULL DEFAULT false,
  enabled         boolean NOT NULL DEFAULT false,
  rate_limit_ms   int NOT NULL DEFAULT 5000,
  priority        int NOT NULL DEFAULT 100        -- nhỏ hơn = ưu tiên hơn
);

CREATE TABLE lottery_draws (
  id               text PRIMARY KEY,                 -- 'mn-tp-hcm-2026-10-26', 'vl-power655-2026-10-29'
  game             text NOT NULL CHECK (game IN ('xs', 'power655')),
  region_code      text NOT NULL REFERENCES regions(code),
  province_code    text NOT NULL REFERENCES provinces(code),
  draw_date        date NOT NULL,
  draw_seq         int,                              -- số kỳ của Vietlott
  scheduled_at     timestamptz NOT NULL,
  warn_at          timestamptz,
  critical_at      timestamptz,
  alert_level      smallint NOT NULL DEFAULT 0,      -- 0 chưa báo, 1 đã báo thường, 2 đã báo nghiêm trọng
  status           text NOT NULL DEFAULT 'scheduled'
                   CHECK (status IN ('scheduled','collected','validated','verified','published','needs_review')),
  current_version  int,
  published_at     timestamptz,
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (province_code, draw_date)                  -- NFR05: không trùng kỳ quay
);
CREATE INDEX ON lottery_draws (region_code, draw_date DESC) WHERE current_version IS NOT NULL;
CREATE INDEX ON lottery_draws (status, scheduled_at) WHERE status <> 'published';

CREATE TABLE raw_fetches (
  id            bigserial PRIMARY KEY,
  source_code   text NOT NULL REFERENCES data_sources(code),
  draw_id       text REFERENCES lottery_draws(id),
  url           text,
  fetched_at    timestamptz NOT NULL DEFAULT now(),
  http_status   int,
  sha256        text,
  file_path     text,
  parse_status  text NOT NULL DEFAULT 'pending'
                CHECK (parse_status IN ('pending','ok','partial','invalid','parse_error','fetch_error')),
  error         text
);
CREATE INDEX ON raw_fetches (draw_id, source_code, fetched_at DESC);

CREATE TABLE result_candidates (
  id           bigserial PRIMARY KEY,
  draw_id      text NOT NULL REFERENCES lottery_draws(id),
  source_code  text NOT NULL REFERENCES data_sources(code),
  fetch_id     bigint REFERENCES raw_fetches(id),
  payload      jsonb NOT NULL,                     -- {"db": ["472899"], "g1": ["78600"], ...}
  is_complete  boolean NOT NULL,
  checksum     text NOT NULL,
  created_by   text,                               -- người nhập tay, nếu có
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (draw_id, source_code, checksum)
);
CREATE INDEX ON result_candidates (draw_id, created_at DESC);

CREATE TABLE draw_versions (
  draw_id       text NOT NULL REFERENCES lottery_draws(id),
  version       int  NOT NULL,
  status        text NOT NULL CHECK (status IN ('needs_review','verified','published','superseded')),
  candidate_id  bigint REFERENCES result_candidates(id),
  reason        text,
  created_by    text NOT NULL,
  verified_by   text,
  verified_at   timestamptz,
  PRIMARY KEY (draw_id, version)
);

CREATE TABLE lottery_results (
  draw_id     text NOT NULL,
  version     int  NOT NULL,
  prize_code  text NOT NULL,
  position    smallint NOT NULL,
  number      text NOT NULL CHECK (number ~ '^[0-9]+$'),
  PRIMARY KEY (draw_id, version, prize_code, position),
  FOREIGN KEY (draw_id, version) REFERENCES draw_versions(draw_id, version)
);

CREATE TABLE audit_logs (
  id         bigserial PRIMARY KEY,
  at         timestamptz NOT NULL DEFAULT now(),
  actor      text NOT NULL,
  action     text NOT NULL,
  entity     text NOT NULL,
  entity_id  text NOT NULL,
  before     jsonb,
  after      jsonb
);
CREATE INDEX ON audit_logs (entity, entity_id, at DESC);

-- US-011: nhật ký chỉ được thêm, không được sửa hay xóa
CREATE FUNCTION audit_logs_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_logs chỉ cho phép thêm dòng mới';
END $$;
CREATE TRIGGER audit_logs_no_update BEFORE UPDATE OR DELETE ON audit_logs
  FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only();

CREATE TABLE outbox_events (
  id            bigserial PRIMARY KEY,
  topic         text NOT NULL,                     -- draw.started, prize.updated, draw.completed, draw.published, draw.corrected
  region_code   text,
  payload       jsonb NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  published_at  timestamptz
);
CREATE INDEX ON outbox_events (id) WHERE published_at IS NULL;

CREATE TABLE source_health (
  id           bigserial PRIMARY KEY,
  source_code  text NOT NULL REFERENCES data_sources(code),
  checked_at   timestamptz NOT NULL DEFAULT now(),
  ok           boolean NOT NULL,
  latency_ms   int,
  error        text
);
CREATE INDEX ON source_health (source_code, checked_at DESC);
