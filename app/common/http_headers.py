"""HTTP header names and values more than one domain sends."""

CACHE_CONTROL_HEADER = "Cache-Control"
RETRY_AFTER_HEADER = "Retry-After"
# Responses that must never sit in a browser or proxy cache: tokens, live health.
NO_STORE = "no-store"
