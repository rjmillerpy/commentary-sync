# Build log

This repository is a public mirror, exported from a private repository through
an allowlist. The production sync matcher stays private; this code runs the
baseline matcher behind the same interface (`app/sync/matcher.py`). The private
history is not published, so this log records the engineering milestones in
order instead.

## 2026-10-07: foundations

- A command-line prototype that finds how far one recording of a broadcast is
  behind another (`sync-offset`), and a synthetic benchmark (`sync-benchmark`).
- Makefile, pre-commit hooks (ruff, mypy strict, Bandit, Trufflehog), and CI
  for lint, tests and secret scanning on every push. Dependabot for uv and
  GitHub Actions.
- The FastAPI skeleton with health endpoints; a multi-stage, non-root Docker
  image; a compose stack with a smoke test in CI.
- Async SQLAlchemy and Redis; Alembic migrations applied on container start.

## 2026-10-15: data, accounts and rules

- NFL and NBA games imported from ESPN, with list and detail endpoints, kept
  current by a scheduler service.
- Accounts with rotating refresh tokens, login lockout, and per-IP rate limits.
- The code-quality rules enforced in tests: mirrored test files, module and
  function size, nesting, annotations, parametrize ids.
- JSON logs from every process, with request and account IDs.

## 2026-10-16: going live

- Commentators with permanent handles and public profiles.
- Streams: commentators go live on a game; LiveKit carries the audio, with
  per-stream room tokens.
- Streams end by themselves when the commentator leaves or the game ends
  (LiveKit webhooks plus the scheduler).
- The broadcaster studio (Next.js): sign in, pick a game, mic check, go live.

## 2026-10-18: listening behind live

- Every stream recorded as HLS by LiveKit Egress, so listeners can play it
  delayed to match their TV.

## 2026-10-19: the listener app and TV sync

- Playwright end-to-end tests against an offline compose stack.
- The API client shared by both apps as an npm workspace.
- The listener app (Expo): pick a game and a commentator, hear them delayed.
- TV sync by sound: the studio sends the commentator's room audio as a
  reference, and a listener's recording of their own TV is matched against it.

## 2026-10-20: hardening and deployment

- Live listener counts in Redis.
- Production hardening: security headers, a deny-all API CSP and a nonce CSP
  for the studio, request size limits, global rate limits.
- Sync features computed on the phone: only features of the TV's sound leave
  it, never audio.
- The AWS deployment as Terraform (ECS Fargate, ALB, S3 and CloudFront for
  HLS, SSM, alarms, budgets, a GitHub OIDC deploy role), tested offline with
  mock providers, tflint and Checkov, and never applied.
- The listener app keeps itself in sync: automatic re-checks, and recovery
  from lost connections.
- The open-core split: the matcher interface, the public baseline, contract
  tests every matcher must pass, and this mirror.
