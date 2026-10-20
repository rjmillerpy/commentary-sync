# commentary-sync

[![CI](https://github.com/rjmillerpy/commentary-sync/actions/workflows/ci.yml/badge.svg)](https://github.com/rjmillerpy/commentary-sync/actions/workflows/ci.yml)

Independent commentary over a live TV broadcast, delayed to match each
viewer's feed. A commentator goes live from a browser studio (`web/`, Next.js)
while watching a game on TV; listeners hear them in a phone app (`listener/`,
Expo), and tap **Sync with my TV** so the commentary lines up with their own
TV, which may be seconds or minutes behind or ahead. The backend is a FastAPI
API (`app/`) with LiveKit for live audio and HLS for delayed listening, and
`infra/` holds its AWS deployment as Terraform.

Sync uses sound only: no game clock, and nothing for the commentator to do.
`sync-offset` runs the same matching on two recordings from the command line,
and `sync-benchmark` measures its accuracy on a synthetic broadcast.

**Open core.** The matcher that places a phone's recording in the
commentator's audio is a private package; this code finds it through one
interface (`app/sync/matcher.py`). Without it, the app runs the baseline
behind the same interface (`app/sync/baseline.py`, plain normalised
cross-correlation), which passes the same contract tests, so everything here
runs end to end. The public repo is a read-only mirror exported from the
private one through an allowlist; its BUILD_LOG.md records the milestones.

[CODE_QUALITY_RULES.md](CODE_QUALITY_RULES.md) holds the rules all code follows.

## Setup

    make install        # uv sync --locked, npm ci for the JavaScript workspaces, then the git pre-commit hook

The JavaScript side needs Node 24 and npm. It is one set of npm workspaces
(the root `package.json` and `package-lock.json`): `client/`, the API client
both apps share, `web/`, the studio, and `listener/`, the listener app.

No system ffmpeg is needed; PyAV bundles its own decoders, so phone recordings
(`.m4a`, `.mp3`, `.wav`, ...) load directly.

## Commands

    uv run sync-offset locate REFERENCE QUERY
    uv run sync-offset compare FEED_A FEED_B [--chunk 10] [--step 30]
    uv run sync-benchmark [--trials 25] [--seed 7]

`locate` exits 0 on a confident match, 1 on no match, 2 on an error.

`compare` probes feed B every `--step` seconds and prints the lag against feed
A, then says which feed is behind. A steady lag means the feeds hold a fixed
distance apart. A jump means a pause, a rebuffer or a different ad break.

Development:

    make lint           # every pre-commit hook on every file
    make test           # tests + coverage, floor 90%
    make web-check      # the studio: eslint, tsc --noEmit, Jest with a 90% floor
    make check          # all three: what CI checks
    make benchmark      # synthetic accuracy benchmark, about 30 s
    make web-dev        # the studio with hot reload on :3000, against `make up`'s API
    make listener-check # the listener app: eslint, tsc --noEmit, Jest with a 90% floor
    make listener-dev   # the listener app in Expo's dev server, for Expo Go on a phone
    make infra-check    # the AWS deployment, offline: fmt, validate, tests, tflint, Checkov
    make e2e            # end-to-end tests in a browser against a separate offline stack, about 45 s

## The API

    make up                                   # API + Postgres + Redis, waits until healthy
    curl http://localhost:8000/health         # readiness: database and Redis answer
    curl http://localhost:8000/health/live    # liveness: the process is up
    make down

So far the API has its foundations, the health endpoints, accounts and
read-only events:

- `GET /health` returns 200 with `{"status": "ok", "checks": {"database": "ok",
  "cache": "ok"}}`, or 503 with the failing check marked `unavailable`. The
  cause goes to the log, never the response. `GET /health/live` checks nothing
  but the process, so an outage elsewhere doesn't get the container restarted.
- Every response carries an `X-Request-ID` header, and every log line written
  during the request carries the same ID. An unexpected error returns
  `{"detail": "Internal server error", "request_id": "..."}`.
- **Logs are JSON**, one object per line, from every process: the API,
  uvicorn, migrations and the scheduler
  ([app/common/logs.py](app/common/logs.py)). Lines in a request carry
  `request_id`, and `account_id` once the request is signed in, so one
  user's report finds every line it caused:

      {"request_id": "16860d67...", "account_id": null, "method": "POST",
       "path": "/auth/login", "status": 401, "duration_ms": 59.7,
       "level": "info", "logger": "app.access",
       "timestamp": "2026-10-15T16:38:28.037070Z", "message": "POST /auth/login 401"}

  Each request gets one access line (method, path, status, duration).
  It leaves out the query string and the client's IP address; uvicorn's
  own access log, which has the IP, is off. Health probes log at debug.
  `COMMENTARY_LOG_LEVEL` applies to the app, uvicorn and Alembic. Other
  libraries log warnings only at any level, because at debug the database
  driver logs statements with their parameters (emails, password hashes) and
  the HTTP client logs full URLs. `COMMENTARY_LOG_FORMAT=console` prints
  readable text instead, for local work.
- Settings come from `COMMENTARY_*` environment variables
  ([app/common/config.py](app/common/config.py)); the app refuses to start
  without `COMMENTARY_DATABASE_URL`, `COMMENTARY_CACHE_URL`,
  `COMMENTARY_AUTH_SECRET` (at least 32 characters) and the LiveKit trio
  `COMMENTARY_LIVEKIT_URL`, `COMMENTARY_LIVEKIT_API_KEY` and
  `COMMENTARY_LIVEKIT_API_SECRET` (at least 32 characters). The compose stack
  supplies local-only values for all of them.
- A rejected request gets a 422 that says which field is wrong and why, but
  never echoes the value sent, which could be a password.
- Async end to end: async SQLAlchemy on psycopg, `redis.asyncio`, one database
  pool and one Redis client per process, each with timeouts. The two health
  pings run at the same time.

### Accounts

    curl -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
         -d '{"email": "fan@example.com", "password": "at least twelve chars", "display_name": "Fan"}'
    curl localhost:8000/auth/me -H "Authorization: Bearer ACCESS_TOKEN"

| Endpoint | Does |
|---|---|
| `POST /auth/register` | creates an account and signs it in: 201 with a token pair, 409 if the email is taken |
| `POST /auth/login` | email and password for a token pair; 401 if wrong, 429 when locked out |
| `POST /auth/refresh` | a refresh token for a new pair; the old refresh token stops working |
| `POST /auth/logout` | signs that device out (204, also when already signed out) |
| `GET /auth/me` | the signed-in account; 401 without a valid access token |

How it works ([app/auth](app/auth)):

- **Passwords** are 12–256 characters, hashed with Argon2id (64 MiB, about
  50 ms each) in a worker thread, at most four at a time, so a burst of logins
  can't block the event loop or use gigabytes of memory. Hashes made with older
  settings are upgraded at the next login. Emails are stored lower-case.
- **Access tokens** are HS256 JWTs that last 15 minutes. Every request reads
  the account, so ending its sessions stops its tokens at once, not when they
  expire. Other domains require sign-in with `Depends(current_user)`.
- **Refresh tokens** last 30 days and work once: refreshing spends the token
  in a single `UPDATE` and issues a new pair, so two requests racing with one
  token can't both win. Only a SHA-256 hash is stored. A spent token presented
  again means it was copied, so every session of that account is ended and
  the user signs in again. Signing out deletes the session instead, so a
  signed-out client retrying its old token isn't taken for an attacker.
- **Lockout.** Five wrong passwords for one account lock it for 15 minutes from the
  first of them, even for the right password (429 with `Retry-After`). The
  count lives in Redis under a hash of the email, with its expiry set in the
  same transaction, so a lockout always ends by itself. Unknown emails count
  too and take as long to reject as a wrong password, so neither the timing
  nor the lockout reveals who has an account. If Redis is down, login returns
  503 rather than allow unlimited guesses.
- **Rate limits per client IP**
  ([app/common/rate_limit.py](app/common/rate_limit.py)): login 10 a minute
  and 100 an hour, register 5 an hour, refresh 30 a minute. Over the limit is
  429 with `Retry-After`. The lockout stops guessing one account's password;
  these stop one client guessing across many accounts or creating them in
  bulk. X-Forwarded-For is ignored, since anyone can set it; IPv6 clients are
  counted per /64, so rotating addresses inside one doesn't help. Redis keys
  hold a hash of the address. If Redis is down the limits are skipped (with a
  warning) rather than taking the routes down; login still fails closed
  through its lockout. Any route can take a limit with
  `dependencies=[Depends(rate_limited(RateLimit("name", limit=..., window_seconds=...)))]`.
- No email address or password is ever logged; accounts appear in logs by ID.

Not built yet: email verification and password reset (both need an email
sender: Amazon SES is about $0.10 per 1,000 emails; a console stand-in is the
free first step), and "sign out everywhere". A lockout can be triggered by
anyone who knows an email, which is the usual trade-off; the per-IP limits are
what stop the guessing itself. A botnet with many addresses still gets
through them; that is a WAF's job once deployed (💲 AWS WAF is about $5/month
plus $1 per rule). Behind the load balancer every request arrives from the
balancer's address, so uvicorn must run with `--forwarded-allow-ips` set to
it, or every client would share one limit.
Two tabs refreshing with the same token at the same moment count as reuse
and sign the user out; a few seconds' grace for the previous token would fix
that once a web client exists.

### Events

Events are NFL and NBA games, imported from ESPN's public scoreboard API:

    make up                                    # the scheduler imports on start
    make events                                # or import the next 7 days by hand
    curl "http://localhost:8000/events?league=nfl"
    curl http://localhost:8000/events/EVENT_ID

`GET /events` lists games from four hours ago onward in start order, so games
in progress show. It takes `league` (`nfl` or `nba`), `starts_after` (an ISO
date-time), `limit` (1–100, default 50) and `offset`, and returns
`next_offset` (`null` on the last page). Each event carries its national TV
networks, for example `["CBS"]`, which is how a viewer will say which feed they
are watching. Games shown only on regional channels have an empty list.

The `scheduler` service in the compose stack
([app/events/scheduler.py](app/events/scheduler.py)) keeps them current. On
start and every 6 hours it re-imports both leagues from yesterday to a week
ahead, picking up new games and changed start times or networks. Every 5
minutes in between, it refreshes yesterday and today for any league with a game
on (from 30 minutes before a kickoff to 4 hours after), so statuses move to
`live` and `final`. A failed import is logged and tried again next cycle; the
service's healthcheck fails if no cycle has finished for 15 minutes. That is
about 900 requests to ESPN on a busy NFL Sunday and about 70 on a quiet day.
The intervals and window are `COMMENTARY_EVENT_*` settings in
[app/common/config.py](app/common/config.py).

    docker compose logs -f scheduler                       # what each cycle imported
    docker compose exec scheduler python -m app.events.scheduler --once   # one cycle now

Both the scheduler and the by-hand importer (`uv run events-import --league
nfl --days 7`) fetch one day per request, retry network errors, 429s and 5xx up
to three times with backoff, and update games they have seen before rather than
adding them again.

**About the data source.** ESPN's API is free and needs no key, but it is
undocumented and unofficial: ESPN publishes no terms for it, and it can change
or be blocked without notice. It is fine for development; check its use with
the lawyer before launch. Everything ESPN-specific is in
[app/events/espn.py](app/events/espn.py), so a licensed provider can replace
it. The alternatives checked on 2026-10-15:

| Provider | Cost | Why not now |
|---|---|---|
| TheSportsDB | free key; about $9/month premium | the free key returns at most 5 events per league per day (an NFL Sunday has 12+); no TV networks |
| balldontlie | free 5 requests/min; NFL and NBA together $159.99/month | needs a key; no TV networks seen on the free tier |
| Sportradar, SportsDataIO | paid, licensed | the production option once there is a budget |

### Commentators

Any account can become a commentator by picking a handle. Listeners find
commentators by handle; the profile shows the account's display name and a
bio, never its email.

    curl -X POST localhost:8000/commentators -H "Authorization: Bearer ACCESS_TOKEN" \
         -H 'Content-Type: application/json' -d '{"handle": "bears_by_the_lake", "bio": "Every snap."}'
    curl localhost:8000/commentators/bears_by_the_lake

| Endpoint | What it does |
|---|---|
| `POST /commentators` | the signed-in account becomes a commentator: 201 with the profile; 409 if it already is one or the handle is taken |
| `GET /commentators` | anyone: one page of commentators by handle (`limit`, `offset`, `next_offset` as for events) |
| `GET /commentators/me` | the signed-in account's profile; 404 for a listener |
| `PATCH /commentators/me` | change the bio (`{"bio": "..."}`) |
| `GET /commentators/{handle}` | anyone: one commentator; 404 if no one has that handle |

A handle is 3–30 letters, digits or underscores, stored lower-case, so `Bob`
and `bob` are one handle and a link works in either case. Handles can't be
changed: a link to a commentator never starts pointing at someone else. Which
of the two unique indexes refused a sign-up (account or handle) is worked out
after the insert fails, so two requests racing get the right 409 on Postgres
and SQLite alike (checked against the compose stack on 2026-10-16).

### Streams

A stream is a commentator live on one event. Listeners list who is live on
their game and pick one:

    curl -X POST localhost:8000/streams -H "Authorization: Bearer ACCESS_TOKEN" \
         -H 'Content-Type: application/json' -d '{"event_id": "EVENT_ID"}'
    curl "localhost:8000/streams?event_id=EVENT_ID"

| Endpoint | What it does |
|---|---|
| `POST /streams` | the signed-in commentator goes live: 201; 403 for a listener; 404 for an unknown event; 409 if the event is final, cancelled or postponed, or the commentator is already live |
| `POST /streams/{id}/end` | end your own stream; 404 for anyone else's (the same answer as a missing one), 409 if already ended |
| `GET /streams` | anyone: live streams, longest-running first, optionally for one `event_id`; paged like events |
| `GET /streams/{id}` | anyone: one stream, `live` or `ended` |
| `POST /streams/{id}/listening` | any signed-in account: "I'm listening", sent by the listener app every 20 s while it plays; 204; 409 once ended; 30 a minute per address |

Every stream carries `listeners`: the accounts that checked in within the last
minute (`COMMENTARY_LISTENER_WINDOW_SECONDS`), each counted once however many
devices it plays on. They're kept in Redis, a sorted set per stream scored by
last check-in, and a whole page of streams is counted in one round trip. An
ended stream has 0. If Redis is down the count is `null` and lists still load;
a check-in gets a 503. The studio shows the count while live (re-read every
10 s), and the listener app shows it beside each commentator.

A stream is live until it has an `ended_at`; there is no separate status
column to disagree with it. One live stream per commentator is a partial
unique index (`WHERE ended_at IS NULL`), so two "go live" requests at once get
one 201 and one 409, checked against Postgres on 2026-10-16.

### Audio

Commentary audio goes through LiveKit, an open-source WebRTC media server, in
the compose stack as the `livekit` service ($0; LiveKit Cloud has a free tier
for later). Each stream has one room, `stream-<id>`. The API never carries
audio: it decides who may join a room, and as what, by signing a LiveKit
token ([app/streams/livekit.py](app/streams/livekit.py)).

| Endpoint | Who | Token lets the client |
|---|---|---|
| `POST /streams/{id}/publisher-token` | the stream's own commentator | send microphone audio (never camera or screen) |
| `POST /streams/{id}/listener-token` | any signed-in account | hear the room, hidden from everyone in it |

Both return `{url, room, token, expires_in}`, refuse ended streams with 409,
are limited to 30 per minute per client, and are never cached. A client
connects to `url` with `token` using any LiveKit SDK (web, React Native,
Android); the token only has to be used within 10 minutes
(`COMMENTARY_LIVEKIT_TOKEN_SECONDS`).

Checked end to end on 2026-10-16 with LiveKit's Python SDK against the
compose stack: a commentator published a 440 Hz tone with an API-issued token,
a listener with its own token heard it at full level, the commentator could not
see the listener, and LiveKit refused the listener's attempt to publish ("no
permission to publish track"). The same run found that a publisher token
without subscribe permission never finishes connecting (the SDKs wait for that
connection), so publisher tokens allow it; a regression test keeps it that way.

Locally, LiveKit tells clients to send media to its container address, which
this machine reaches directly; only signalling (7880) is published. A phone on
the same Wi-Fi needs LiveKit's `rtc.node_ip` set to the laptop's LAN address
and ports 7881/tcp and 7882/udp published on it. WebRTC plays audio as soon as
it arrives; for listeners who need it held back, see [Delayed listening
(HLS)](#delayed-listening-hls).

Streams end on their own, so a commentator who closes the tab or loses signal
isn't listed as live forever. LiveKit posts room and participant events to
`POST /webhooks/livekit`, which accepts only notices signed with the LiveKit
API secret and carrying the body's hash (anything else is a 401):

- the commentator's connection dropping marks the stream; their next
  connection clears the mark. A reload connects anew before the old connection
  drops, so it never counts;
- the room closing (everyone, listeners too, gone for 20 s) ends the stream;
- each scheduler cycle ends streams whose commentator has been gone longer
  than `COMMENTARY_STREAM_AUDIO_GRACE_SECONDS` (2 minutes) and streams on
  games that are final, cancelled or postponed. Cycles run every 5 minutes, so
  a dropped stream ends 2 to 7 minutes after its commentator leaves.

Checked end to end on 2026-10-17 against the compose stack: a reload, a drop
and a return were tracked, the room closing ended its stream, and a scheduler
run ended a stream whose commentator had left while a listener stayed. LiveKit
delivered 15 webhooks; none was rejected.

### Delayed listening (HLS)

A listener's TV is usually behind the commentator's, often by 30 s or more on
a streaming service, so the commentary has to wait for it. WebRTC can't wait:
it plays what arrives. So every stream is also recorded as HLS, short audio
segments and a playlist, which a player can play any distance behind live.
Each segment carries the wall-clock time it was recorded
(`#EXT-X-PROGRAM-DATE-TIME`), which later sync work can align to.

    curl -X POST localhost:8000/streams/STREAM_ID/listener-playlist -H "Authorization: Bearer ACCESS_TOKEN"
    # {"url": "http://localhost:8080/<random path>/index.m3u8"}

| Endpoint | Who | Returns |
|---|---|---|
| `POST /streams/{id}/listener-playlist` | any signed-in account | `{url}` of the stream's playlist; 409 until the commentator's audio connects ("no HLS audio yet") and after the stream ends; same rate limit as room tokens; never cached |

How it works ([app/streams/recorder.py](app/streams/recorder.py)):

- the commentator's first connection (the `participant_joined` webhook)
  makes the API ask LiveKit Egress, the `egress` service, to record the
  stream's room into a random directory. The directory is claimed in the
  database first, so two joins at once start one recording; a failed start is
  retried on the next join, and listeners keep WebRTC meanwhile;
- Egress joins the room as a hidden recorder and writes 2 s AAC segments
  (`COMMENTARY_HLS_SEGMENT_SECONDS`). It records the room, not the
  commentator, so a reload doesn't break the playlist: the gap is silence and
  the timeline stays true;
- the `hls` service (nginx, read-only, [deploy/hls-nginx.conf](deploy/hls-nginx.conf))
  serves the files on `localhost:8080`; the playlist is never cached, segments
  are immutable;
- ending the stream, or the scheduler ending it, stops the recording, which
  closes the playlist (`#EXT-X-ENDLIST`). The room closing ends it on its own.

The random path is the only key to a recording: it is handed out only to
signed-in accounts and never logged. A deployed stack uploads to S3 behind
CloudFront, where signed cookies can replace the path as the key. HLS is on
when `COMMENTARY_LIVEKIT_API_URL` (where the API reaches LiveKit's server API)
and `COMMENTARY_HLS_BASE_URL` (where listeners fetch) are both set; with
neither, streams are WebRTC only.

Numbers, from the compose stack on 2026-10-18: the playlist is up 3 s after
the commentator's mic connects, and the newest segment ends within 0.2 to
1.2 s of the time it is fetched. So HLS runs about 2 to 3 s behind the
commentator. That's fine for this use, because listeners delay it further
anyway. A listener whose TV is less than that behind the commentator's can
use WebRTC instead. Segments are about 42 KB per 2 s (MPEG-TS overhead on small audio
frames), so about 76 MB per stream-hour stored and per listener-hour
delivered. The local volume is in memory, 1 GB (about 13 stream-hours), and
emptied by `make down`. Egress used about 50 MB of memory recording one
stream.

Checked end to end on 2026-10-18 with LiveKit's Python SDK against the
compose stack: before the commentator connected the playlist was a 409; after,
a listener's playlist segments decoded to the commentator's 440 Hz tone; after
a reload the URL was the same and the playlist continued without a break; and
ending the stream closed the playlist. The random path appeared in no API log
line.

### Migrations

The schema is built only by Alembic migrations in
[alembic/versions](alembic/versions). The container runs `alembic upgrade
head` before it starts serving; a Postgres advisory lock means that when
several containers start together, one migrates and the others wait.

To change the schema: edit or add a `models.py` under a domain in `app/`
(every `app/*/models.py` is picked up automatically), then

    make up
    make migration m="add commentators"

and read the generated file before committing it. `make up` again applies it.
The tests run every migration up and down, and fail if the models and the
migrations disagree; CI repeats that check against real Postgres.

The stack's Postgres is published on `localhost:5434`.

The image ([Dockerfile](Dockerfile)) is multi-stage and runs as a non-root
user on a read-only filesystem: 642 MB, against 2.35 GB for a single-stage
build on the full Python image. numpy, scipy and PyAV are 346 MB of it. A cold
`make up` takes about 40 s; `docker stop` shuts down in under a second after
closing the pool.

### Production hardening

- **Security headers on every response:** `nosniff`, `X-Frame-Options: DENY`,
  `no-referrer`, and a Content-Security-Policy that allows nothing
  (`default-src 'none'`), since the API serves JSON, never pages. The docs pages
  are the exception, and a deployed API turns them off
  (`COMMENTARY_API_DOCS=false`). Strict-Transport-Security once served over
  HTTPS (`COMMENTARY_HSTS_SECONDS`).
- **A cap on every request body** (`COMMENTARY_MAX_REQUEST_BYTES`, 2 MB), checked
  before any endpoint reads it. A declared length over it gets a 413 at once;
  a chunked body is counted and cut off.
- **Rate limits per client address, on top of the per-endpoint ones:**
  - 300 requests a minute across all public routes (not health checks or
    LiveKit's webhook);
  - going live and ending, 10 a minute;
  - becoming a commentator and editing the profile, 20 an hour, which also
    slows anyone guessing handles.

  Behind a load balancer, uvicorn must trust it to report client addresses
  (`FORWARDED_ALLOW_IPS`), or every client shares one limit.

## The studio

`web/` is the broadcaster studio, a Next.js app on http://localhost:3000
(`make up` builds and starts it as the `web` service; `make web-dev` runs it
with hot reload). A commentator:

1. signs in or creates an account, then picks a handle if they have none;
2. picks a game that is scheduled or on now;
3. checks their mic: chooses one and watches a level meter (echo
   cancellation, noise suppression and auto gain are on, for talking over a TV);
4. goes live: the studio creates the stream (`POST /streams`), gets a
   publisher token and sends the mic to the stream's LiveKit room; and ends it.

If LiveKit loses the connection it reconnects on its own and the studio says
so. A reload, a crash or LiveKit giving up leaves the stream live in the API
with no audio: the studio finds it on load (`GET /streams?commentator=`) and
offers **Resume** (a new publisher token, same stream) or **End stream**.
Closing the tab while live asks first; if the commentator leaves anyway, the
API ends the stream itself (see Audio).

The browser calls the API directly, so the API allows the studio's origin
(`COMMENTARY_CORS_ORIGINS`, a JSON list of exact origins; compose sets
`["http://localhost:3000"]`). Going direct rather than through a Next.js proxy
keeps the per-IP rate limits seeing each browser's address. The access token
lives only in memory; the refresh token is in `sessionStorage` so a reload
stays signed in, and goes when the tab closes. Pages are served with
`X-Frame-Options: DENY`, `nosniff`, `no-referrer` and a Permissions-Policy that
allows the microphone and nothing else.

Every page also has a Content-Security-Policy ([web/src/lib/csp.ts](web/src/lib/csp.ts),
set by `web/src/middleware.ts`):
- **Scripts:** the studio's own files, plus inline scripts only when they carry
  the nonce made fresh for each request (Next puts it on its own), plus `blob:`
  for the TV-sync AudioWorklet.
- **Styles:** the studio's own stylesheets only.
- **Connections:** the API and the LiveKit server only, so even an injected
  script couldn't send anything elsewhere. Both addresses are baked into the
  build (`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_LIVEKIT_URL`).
- **Never framed.**

Pages are rendered for each request so the nonce reaches them. Every
end-to-end test fails on any CSP violation in the browser, and one checks that
every script on the page carries the nonce.

livekit-client, the largest dependency, loads only when going live; the page
itself is about 30 kB. Packages are pinned exactly and installed with
`--ignore-scripts`. `npm audit --omit=dev` is clean; the dev-only tools (Jest,
eslint) pull in `braces` and `sprintf-js`, which have advisories and no fixed
release, and only ever read this repo's own files.

The API calls, response schemas (zod) and the signed-in session come from
`client/`, the `@commentary-sync/client` workspace, which the listener app
uses too. It is TypeScript source with no build step: Next compiles it with
the studio (`transpilePackages`), and its own tests run on Node's built-in
test runner, which runs TypeScript directly, so it has no test dependencies
(`make client-check`: tsc, then `node --test` with a 90% floor; 100% now).
Because the studio is a workspace, its image builds from the repository root
(`web/Dockerfile`, with `web/Dockerfile.dockerignore` keeping the context to
the two workspaces).

Tests (`web/__tests__/`, mirroring `src/`, checked by
`__tests__/test_structure.test.ts`) fake only the boundaries: `fetch` (the API),
the browser's microphones and Web Audio, and livekit-client (WebRTC, which jsdom
lacks). Checked end to end on 2026-10-17 in Chromium with its fake microphone
against the compose stack: sign up, pick a handle and a game, the meter moved,
go live; a separate LiveKit listener heard the commentator's microphone track;
after a reload the studio offered Resume, and the listener heard it again;
End stream ended it in the API.

## Checks

The same hooks run on `git commit` and in CI
([.pre-commit-config.yaml](.pre-commit-config.yaml)): file hygiene, a
large-file guard, ruff lint and format, Bandit on `app/`, mypy strict, and a
Trufflehog secret scan of the files being committed. The test suite also
checks the measurable [code-quality rules](CODE_QUALITY_RULES.md) on every
file: mirrored tests and module size (`tests/test_structure.py`), and
function, method and class length, nesting and loop depth, broad excepts,
annotations, `parametrize` ids and inheritance depth
(`tests/test_code_rules.py`). The studio's checks (`make web-check`) are
eslint with the measurable rules as errors (nesting, function and module
length, magic numbers), `tsc --noEmit` in strict mode, and Jest with a 90%
floor. `make e2e-check` type-checks the end-to-end tests (strict). The secret hook needs the
`trufflehog` binary on PATH
([install](https://github.com/trufflesecurity/trufflehog#floppy_disk-installation));
versions of everything else are locked in `uv.lock`.

CI ([ci.yml](.github/workflows/ci.yml)) runs on every push: `lint` (the
hooks), `test` (pytest from `uv sync --locked`, with the coverage table on the
run summary and a 90% floor) and `secrets` (Trufflehog on the pushed commits).
When all three pass, `build` builds the image, starts it with a real Postgres
and Redis, checks `/health` and runs `alembic check`. A weekly job scans the full history.
Dependabot opens grouped weekly PRs for Python packages, Docker images and
GitHub Actions.

## The listener app

`listener/` is the listener app, built with Expo (React Native) for iPhone and
Android. A listener:

1. signs in or creates an account (the refresh token is kept in the phone's
   secure storage, Keychain or Keystore, so the app stays signed in);
2. picks a game that is on or coming up, then a commentator live on it;
3. hears them through the stream's HLS recording, held behind real time by a
   delay they nudge (±5 s and ±0.5 s, from 0 to 5 minutes) until the commentary
   matches their TV. Audio keeps playing with the screen off.

How the delay works ([listener/src/lib/delay.ts](listener/src/lib/delay.ts)):
the segments carry the time they were recorded, so the player knows how far
behind real time it is playing. Twice a second the app compares that with the
chosen delay and seeks back or forward to match. If the recording doesn't
reach back far enough yet (a listener 30 s behind, ten seconds into the
stream), it pauses until the delay has built up, the way pausing a TV does,
and says so. expo-video's own live-offset setting would do this only on iOS;
this works on both.

The app uses the shared client (`client/`) for every API call and for the
session, so it behaves like the studio: one refresh at a time, and the same
error sentences. Tests (`listener/__tests__/`, mirroring `src/`) use jest-expo
and React Native Testing Library and fake only the phone's boundaries: `fetch`
(the shared FakeApi), secure storage, and the media player (a fake on a
timeline the test moves, so seeking and holding are checked). 79 tests, 99.5%
statement coverage. `npx expo export` bundles it for Android and iOS (about
720 modules, 2.2 MB of Hermes bytecode each), which proves the workspace and
the shared client resolve under Metro.

Versions: Expo SDK 58 (`expo` 58.0.3) with React Native 0.88.0-rc.3. Every
Expo 58 release from two weeks ago or more bundles that release candidate,
because 0.88.0 itself came out on 2026-10-15; move to it once it is two weeks
old. Expo 58 because the Expo Go app in the stores runs only the newest SDK,
and its React (19.3.0) is the studio's, which keeps the workspace on one copy.
Everything was installed with `npm install --before=2026-10-05`, so transitive
packages are two weeks old too. `npm audit --omit=dev` reports three advisories,
all inside Expo's command-line tools (`expo` is a runtime dependency by Expo's
convention, but these parts run only on the laptop, to serve and bundle the
app; none is in the app itself): `node-forge` and `braces` have no fixed
release yet, and `uuid` would need Expo's tools moved from uuid 7 to 11
underneath them. Recheck when Expo 58 updates.

### Trying it on a phone (free)

Install **Expo Go** from the App Store or Google Play. The phone and the laptop
must be on the same Wi-Fi. Then, with the laptop's address on that network
(`hostname -I`, the first one):

    COMMENTARY_PUBLISH_ADDRESS=0.0.0.0 COMMENTARY_HLS_BASE_URL=http://LAPTOP_IP:8080 make up
    EXPO_PUBLIC_API_URL=http://LAPTOP_IP:8000 make listener-dev

and scan the QR code with the phone (Android: in Expo Go; iPhone: the camera).
`COMMENTARY_PUBLISH_ADDRESS=0.0.0.0` opens the API and the HLS server to
everyone on that Wi-Fi, so only do this on a network you trust, and `make up`
without it afterwards. Go live from the studio on the laptop, then listen on
the phone. To try **Sync with my TV**, play the same game on a TV near the
laptop (its mic is the commentator's) and another near the phone, or one TV
for both. Not covered yet:

- a phone test in CI (an Android emulator with Maestro or Detox);
- store builds. 💲 Google Play is $25 once, Apple $99 a year; EAS Build has a
  free tier, or `npx expo prebuild` builds locally.

## Syncing to the TV by sound

A listener taps **Sync with my TV**. The phone listens to their TV for 10
seconds, and the app sets the delay so the commentary lines up with it. If
their TV is *ahead* of the commentator's, the commentary can't be brought
forward, so the app says how long to pause the TV instead. Nothing about the
game clock is used, so stoppages, resets and broken clocks don't matter, and
the commentator does nothing.

How it works:

1. **The commentator's room is the reference.** While live, the studio opens
   the microphone a second time with echo cancellation, noise suppression and
   auto gain off, so the TV in the background survives (the broadcast keeps
   its own cleaned-up track). An AudioWorklet hands that audio over at 8 kHz,
   and it goes to `POST /streams/{id}/reference` in 5 s chunks of 16-bit PCM.
   The API keeps the last 4 minutes per stream in Redis
   (`COMMENTARY_SYNC_REFERENCE_SECONDS`, about 4 MB per live stream); it is
   never broadcast.
2. **The listener's phone listens to the TV, and the sound never leaves it.**
   For 10 seconds the phone takes raw audio from its microphone
   (expo-audio's PCM stream), mixes it to mono and resamples it to 8 kHz.
   It then computes the matcher's features right there
   ([client/src/features.ts](client/src/features.ts), a port of
   `app/sync`'s): 16 band energies, 100 times a second. From those, the sound
   can't be played back or the words recovered. Only they go to
   `POST /streams/{id}/sync`, about 64 KB; the API no longer accepts audio
   from listeners at all. The matcher finds them in the reference.
   They're matched in memory and never stored or logged.
   - **Parity with Python:** `client/test/features.test.ts` checks the port
     against features `app/sync` computed (a fixture made by
     `client/test/fixtures/features_fixture.py`, which a Python test keeps
     current). The largest difference is 0.000003.
3. **One clock for both.** Every device measures how far its clock is from the
   server's (`GET /clock`, the fastest of three round trips) and stamps its
   audio in server time. So the answer, *when the listener's TV played it
   minus when the commentator's did*, is in seconds, whatever either device's
   clock says.
4. **The app turns that into a delay** ([listener/src/lib/tvSync.ts](listener/src/lib/tvSync.ts)).
   HLS runs 2-3 s behind the commentator, so 4 s is the soonest the
   commentary can play. A TV less behind than that, or ahead, gets "pause your
   TV for N s" and the delay set to 4 s. A TV ahead isn't in the reference
   until the commentator's TV catches up, so "not found" is retried three
   times, 5 s apart. The commentary pauses while the phone listens, or the
   phone would hear it too.

| Endpoint | Who | What |
|---|---|---|
| `GET /clock` | anyone | `{now}`: the server's time, never cached |
| `POST /streams/{id}/reference?captured_at=` | the stream's commentator | a chunk of room audio (raw PCM); 204; 30 a minute |
| `POST /streams/{id}/sync?captured_at=` | any signed-in account | the features of 3-20 s of their TV (frames of 16 little-endian float32 values, 100 a second; never audio); `{status: "matched", delay_seconds, peak_ratio}` or `{status: "not_found"}`; 12 a minute |

Checked:

- API tests with the synthetic broadcast: TVs 7.5 s behind, level, and 4 s
  ahead come back within 0.1 s; a different broadcast is not found.
- In Chromium, end to end (`make e2e`, `tests/sync.spec.ts`): the real studio
  goes live with a fake mic playing seeded noise bursts under the tone; two
  clips of that room, 4 s apart, both match and agree on the delay; another
  room's sound is not found. The clips' features are computed by the phone's
  own code (`client/src/features.ts`, from 48 kHz as a phone delivers it).
- On the phone, these are tested against fakes of the microphone (mono and
  stereo, at 48 kHz) and the API:
  - only features are sent, and they're exactly the shared code's;
  - the capture time;
  - the retries;
  - the pause advice.

### Staying in sync

After the first sync, the app keeps the commentary lined up by itself
([listener/src/lib/autoSync.ts](listener/src/lib/autoSync.ts)).

**The listener's TV can drift.** They pause it, an ad break runs a different
length, or a streaming TV stalls on bad Wi-Fi. Only listening again can tell,
so the app re-checks the TV:
- every 5 minutes while the commentary plays;
- 5 seconds after anything likely to have moved it: the phone's connection
  coming back, the app coming back to the front, or the commentary's own
  playback recovering.

An automatic check listens for 6 seconds (a requested sync, 10) and only
changes the delay when the TV really moved (by more than half a second). It
*mutes* the commentary meanwhile rather than pausing it, so the commentary's
place in time stays put. If the TV has got ahead, the listener is told how
long to pause it. A check that can't hear the TV says nothing the first two
times; after three in a row it says so. **Keep in sync automatically** turns
it off. Nothing is checked before the first sync, or while offline.

**The app's own audio recovers by itself.** It used to stop with "The audio
stopped" when the connection dropped. Now:
- it says "Reconnecting…" and reloads the stream after 1, 2, 4… up to 30
  seconds;
- it reloads at once when the phone's connection comes back;
- the delay control then puts it back at exactly the same delay, since every
  segment carries its recording time;
- a "No connection" banner shows while offline;
- the playlist lookup waits out outages instead of failing;
- check-ins and the stream-ended check already shrugged off failures.

Tested with fakes of the phone's network, app state, microphone and player
(160 tests). One test drops the connection: the audio fails, then reloads the
moment the connection returns and plays at the same delay. Five seconds
later the TV is re-checked, with the commentary muted.

Limits, until tests with real recordings and a real phone say more:

- **The commentator's mic must hear their TV.** If they listen to the TV in
  headphones, there is no reference; the studio says so while live.
- **Different broadcasts of one game** (national and local feeds, with
  different announcers) probably won't match; real recordings will tell. The
  delay nudges are the fallback.
- Two captures of one microphone work in Chromium; Firefox and Safari are
  untested.
- How exactly a phone's recording start lines up with its clock is unmeasured;
  expect a few tenths of a second, which the 0.5 s delay nudges cover.

## End-to-end tests

    make e2e

Playwright drives the real studio in Chromium against the whole stack: the
API, Postgres, Redis, LiveKit, Egress and the HLS server, built from this
checkout. A test passes only if a listener hears the commentator.

| Test | What it proves |
|---|---|
| a commentator goes live and a listener hears them, live and delayed | sign up, pick a handle, pick the game, the mic-check meter moves, go live; a listener in another browser context hears the commentator over WebRTC, then over HLS held 4 s behind live by hls.js; ending the stream ends it in the API and closes the playlist (409) |
| a reload mid-broadcast resumes the same stream | after a reload the studio offers Resume, which continues the same stream (same ID, same playlist URL), and the listener hears it again |
| a listener's TV recording is found in the commentator's room, and gives one delay | the studio records the room raw while live; two clips of the room 4 s apart are matched and agree on the delay; a different room is not found |

How it is set up ([compose.e2e.yaml](compose.e2e.yaml), [e2e/](e2e)):

- **Its own stack:** the compose project `commentary-sync-e2e`, deleted after
  the run, so the dev stack and its data are never touched and either can run
  while the other does.
- **Offline:** the stack runs on an internal Docker network with no internet,
  and publishes no ports. The browser runs inside it, in Playwright's image
  (`mcr.microsoft.com/playwright:v1.63.0-noble`, 3.5 GB, free), and reaches
  each service by name. ESPN is replaced by one seeded game
  ([e2e/seed.sql](e2e/seed.sql)), and the scheduler doesn't run. Checked: a
  request from inside the network to ESPN fails at DNS.
- **A real microphone signal:** Chromium's fake microphone plays a 440 Hz
  tone in pulses of random length (pulsed, so the studio's noise suppression
  doesn't learn it as background noise), over quieter noise bursts from a
  seeded generator, so no part of the minute-long file repeats and the sync
  test has one right answer. The listener's Web Audio analyser
  must find its loudest frequency within 15 Hz of 440 and above -60 dBFS. So
  silence, noise or the wrong stream fails.
- **Browser setup:** the studio is served on `http://web:3000`, which Chromium
  is told to treat as secure, so the microphone works without a test
  certificate. That flag needs the full Chromium build; the headless shell
  ignores it.
- **Accounts:** the suite registers 5 accounts, the API's 5-per-hour limit
  per address; the sync test signs in as its commentator over the API rather
  than registering a listener.

A failure leaves an HTML report and a trace (screenshots, network, console)
in `e2e/results/`; open the trace with `npx playwright show-trace`. Their
first run found a real bug: on a page without a secure connection, opening
the microphone crashed the whole studio. It now says the microphone needs
https; regression tests cover it in the studio's Jest suite.

The e2e tests aren't in `make check`, which only type-checks them, because
they take a full stack build. CI will run them as their own job.

## Deployment

[infra/](infra/README.md) holds the AWS deployment as Terraform:
- ECS Fargate behind a load balancer for the API, the studio and the scheduler;
- a small VM for LiveKit, Egress and Redis;
- S3 and CloudFront for HLS;
- SSM for secrets;
- Route 53 and ACM for DNS and certificates;
- alarms and budgets;
- a GitHub OIDC deploy role.

It is tested offline and has never been applied. `make infra-check` runs the
checks without AWS credentials. Applying it costs about $77 a month
(infra/README.md has the breakdown, cheaper options, and the go-live and
teardown steps), so it waits for a go-ahead. `.github/workflows/deploy.yml`
builds, pushes and deploys, but only when started by hand.

## How it works

Audio is reduced to 16 log-spaced band energies between 300 Hz and 3.6 kHz at
100 frames per second, then differenced in time. Differencing cancels volume
and speaker or microphone EQ. A matcher (`app/sync/matcher.py`) then finds
where the query's features sit in the reference's, and how sure it is. The
baseline slides the query along the reference with normalised
cross-correlation and calls a match confident when its peak stands far above
the scores everywhere else.
