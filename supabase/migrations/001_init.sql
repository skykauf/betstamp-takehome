-- Odds agent: snapshot + denormalized lines (seeded from data/sample_odds_data.json)
-- Optional reference DDL: the FastAPI app also runs equivalent CREATE IF NOT EXISTS + seed on cold start when DATABASE_URL is set.

CREATE TABLE IF NOT EXISTS odds_snapshots (
  id BIGSERIAL PRIMARY KEY,
  label TEXT NOT NULL DEFAULT 'default',
  loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (label)
);

CREATE TABLE IF NOT EXISTS odds_lines (
  id BIGSERIAL PRIMARY KEY,
  snapshot_id BIGINT NOT NULL REFERENCES odds_snapshots (id) ON DELETE CASCADE,
  game_id TEXT NOT NULL,
  sport TEXT NOT NULL DEFAULT 'NBA',
  home_team TEXT NOT NULL,
  away_team TEXT NOT NULL,
  commence_time TIMESTAMPTZ NOT NULL,
  sportsbook TEXT NOT NULL,
  markets JSONB NOT NULL,
  last_updated TIMESTAMPTZ NOT NULL,
  UNIQUE (snapshot_id, game_id, sportsbook)
);

CREATE INDEX IF NOT EXISTS idx_odds_lines_game ON odds_lines (game_id);
CREATE INDEX IF NOT EXISTS idx_odds_lines_book ON odds_lines (sportsbook);
CREATE INDEX IF NOT EXISTS idx_odds_lines_last_updated ON odds_lines (last_updated);

-- Full OpenAI-style message list for multi-turn tool + chat continuity
CREATE TABLE IF NOT EXISTS chat_threads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid (),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now (),
  messages JSONB NOT NULL DEFAULT '[]'::jsonb
);
