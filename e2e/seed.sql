-- The one game the e2e tests commentate. The e2e stack has no internet, so
-- the scheduler can't import games from ESPN; this stands in for it.
INSERT INTO events (id, source, source_event_id, league, title, home_team, away_team, starts_at, status, networks)
VALUES (
    '00000000-0000-4000-8000-000000000e2e',
    'e2e',
    'e2e-game',
    'nfl',
    'Houston Texans at Jacksonville Jaguars',
    'Jacksonville Jaguars',
    'Houston Texans',
    now() - interval '10 minutes',
    'live',
    '["CBS"]'
)
ON CONFLICT DO NOTHING;
