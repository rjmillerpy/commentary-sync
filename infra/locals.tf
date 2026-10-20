locals {
  account_id = data.aws_caller_identity.current.account_id
  ssm_prefix = "/${var.project}"

  hosts = {
    api    = "api.${var.domain_name}"
    studio = "studio.${var.domain_name}"
    live   = "live.${var.domain_name}" # LiveKit: wss signalling and its server API
    hls    = "hls.${var.domain_name}"  # CloudFront in front of the HLS bucket
  }

  # Secrets the containers get from SSM Parameter Store, by environment
  # variable name. Terraform creates each parameter with a placeholder and
  # never reads it back; set-secrets.sh puts the real values, so no secret is
  # in this code, its plans or its state.
  api_secrets = {
    COMMENTARY_DATABASE_URL       = "database-url"
    COMMENTARY_CACHE_URL          = "cache-url"
    COMMENTARY_AUTH_SECRET        = "auth-secret"
    COMMENTARY_LIVEKIT_API_KEY    = "livekit-api-key"
    COMMENTARY_LIVEKIT_API_SECRET = "livekit-api-secret"
  }
  # The VM's own: the same LiveKit key pair, and Redis's password.
  livekit_secrets = ["livekit-api-key", "livekit-api-secret", "redis-password"]
  all_secrets     = toset(concat(values(local.api_secrets), local.livekit_secrets))

  log_retention_days = 14
  ports = {
    api          = 8000
    web          = 3000
    livekit_http = 7880 # signalling behind Caddy, and the server API the API calls
    redis        = 6379
    https        = 443
    http         = 80
    ice_tcp      = 7881
    ice_udp      = 7882
  }
}
