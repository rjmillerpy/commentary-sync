# infra/: the AWS deployment (roadmap Phase 1.5, D9-D17)

**Written in $0 mode.** Everything here is formatted, validated, linted
(tflint, Checkov) and tested offline against mock providers. None of it has
been applied: nothing exists in AWS and nothing is billed until the user says
go. The deploy workflow (`.github/workflows/deploy.yml`) only runs when
started by hand.

```
                         internet
      ┌──────────────────────┼─────────────────────────┬──────────────────┐
      │ :443 (:80 redirects) │ :443 wss, :7881 tcp,    │ :443             │
      │                      │ :7882 udp (media)       │                  │
┌─────▼──────────┐   ┌───────▼─────────────┐   ┌───────▼────────┐  ┌──────▼───────┐
│ ALB (2 zones)  │   │ LiveKit VM (EIP)    │   │ CloudFront     │  │ Neon         │
│ api.<domain>   │   │ Caddy (TLS) LiveKit │   │ hls.<domain>   │  │ Postgres     │
│ studio.<domain>│   │ Egress Redis        │   │ (OAC)          │  │ (free plan)  │
└──┬─────────┬───┘   └──┬───────────────▲──┘   └───────▲────────┘  └──────▲───────┘
   │         │          │ s3:PutObject  │ Redis,       │ GetObject        │
┌──▼──┐   ┌──▼──┐       │ hls/*         │ server API   │                  │
│ api │   │ web │   ┌───▼───────────────┼──┐   ┌───────┴────────┐         │
└──┬──┘   └─────┘   │ S3: recordings,   │  │   │                │         │
   │  scheduler     │ deleted after 3 d │  │   └────────────────┘         │
   │  (Spot)        └───────────────────┼──┘                              │
   └────────────────────────────────────┴─────────────────────────────────┘
        Fargate, public subnets, no NAT gateway; only the ALB reaches the tasks
```

## What it costs once applied (us-east-2, estimates; check current prices)

| Item | $/month |
|---|---|
| Application Load Balancer (plus a little traffic) | about 18 |
| Fargate: API and studio, ¼ vCPU and 0.5 GB each | about 18 |
| Fargate Spot: the scheduler | about 3 |
| EC2 t3a.small for LiveKit, Egress and Redis, with 20 GB gp3 | about 15 |
| Public IPv4 addresses ($0.005/hour each): 3 tasks, the VM, the ALB's 2 | about 22 |
| Route 53 hosted zone; the domain itself (about $12 a year) | about 1.50 |
| CloudFront, S3, CloudWatch, SSM, ECR at test-group size | about 0 (free tiers) |
| Neon Postgres (free plan) | 0 |
| **Total** | **about 77** |

That is more than the roadmap's early guesses, mostly because AWS now
charges for every public IPv4 address and the design runs three always-on
tasks. Cheaper ways, if wanted:

- **One VM running `compose.yaml` as it is** (API, studio, scheduler,
  LiveKit, Egress, Redis, Caddy) is about $15-30 a month. It gives up the
  load balancer, rolling deploys and the ECS learning.
- **The scheduler as a scheduled task** (EventBridge, `--once` every 5
  minutes) saves about $5.
- **The studio on a free static or edge host** saves about $12. It would
  need its CSP moved from the Next middleware.

**Before applying:** turn on the `project` cost allocation tag (Billing >
Cost allocation tags), so the two budgets (warnings at $5 and $20 a month)
count this project only. Budgets warn; they don't stop anything. The stop is
`terraform destroy`.

## Going live, step by step

1. Register a domain in Route 53 (💲 about $12 a year), which creates its
   hosted zone. Create a free Neon project.
2. `cp backend.hcl.example backend.hcl`, then set an S3 state bucket.
   rad-shift's state bucket is in the same account; use a key of its own.
3. Copy `example.tfvars` to `prod.auto.tfvars` and set `domain_name` and
   `alert_email`.
4. Apply and set the secrets:
   ```bash
   cd infra
   AWS_PROFILE=... terraform init -backend-config=backend.hcl
   AWS_PROFILE=... terraform plan     # read it: what will be created
   AWS_PROFILE=... terraform apply    # 💲 billing starts here
   AWS_PROFILE=... ./set-secrets.sh   # generates secrets; asks for Neon's URL
   ```
5. In GitHub, set the repository variables the deploy workflow lists, from
   `terraform output`. Then run **Actions > deploy > Run workflow** on main.
   The services start on the tag `initial`, which doesn't exist, and fail
   their first health checks until that first deploy pushes real images.
6. Reboot the LiveKit VM once (Session Manager or the console), so it picks
   up the secrets set in step 4.

**Teardown** (between demos, or for good): `terraform destroy`. The HLS
bucket empties itself; the ECR repositories must be emptied first.

## Checks (no AWS credentials needed)

```bash
make infra-check     # terraform fmt -check, validate, test (mock providers), tflint, Checkov
```

They're part of `make check`. Checkov's deliberate exceptions are inline
`checkov:skip` comments, each with its reason; most are about cost (a WAF,
customer KMS keys, access logs, Container Insights).

Checkov is locked apart from the app, in `tools/`. Checkov pins asteval 1.0.6,
which has two sandbox escapes, so `tools/pyproject.toml` overrides it to
1.0.10; `make infra-check` proves Checkov still runs on it. It also pulls in
`ecdsa`, whose timing-attack advisory has no fix; Checkov never signs anything
with it here, and it only ever scans this repo's own Terraform.

## Design decisions, and the test that pins each

| Decision | Why | Test (`tests/main.tftest.hcl`) |
|---|---|---|
| Public subnets, no NAT gateway; tasks reachable only from the ALB | A NAT gateway is about $33/month | `no_nat_gateway_tasks_reachable_only_from_the_load_balancer` |
| Secrets: SSM placeholders Terraform never reads back; `set-secrets.sh` writes them; ECS injects them | No secret in code, plans or state | `secrets_never_in_terraform_or_the_task_definitions` |
| API env: docs off, HSTS, CORS for the studio only, `FORWARDED_ALLOW_IPS` = the VPC, LiveKit's server API over the private network | Production hardening (README, "Production hardening") | `the_api_runs_hardened` |
| One scheduler, on Spot; deploys stop the old one first; every service rolls back a failed deploy | Two would import twice; Spot is 70% cheaper | `exactly_one_scheduler_on_spot` |
| HTTPS only, TLS 1.3/1.2; port 80 redirects; host routing | | `https_only_with_modern_tls` |
| LiveKit VM: IMDSv2, hop limit 1, encrypted disk, exactly 4 public ports; Redis and the server API from the tasks only; Session Manager, no SSH | WebRTC needs UDP and a fixed IP | `the_livekit_vm_is_locked_down` |
| Recordings: a private bucket read only by CloudFront (OAC), deleted after 3 days; playlists uncached, segments cached; TLS 1.2+ | Temporary, and billed while stored | `recordings_are_private_temporary_and_served_over_https` |
| Deploy role: OIDC, this repository's main branch only, every action named | No stored AWS key; no PR or fork can deploy | `the_deploy_role_is_this_repositorys_main_branch_only` |
| 14-day logs, $5 and $20 budgets on this project's tag, one task per service | Cost guards | `cost_guards` |
| Alarms to email: API 5xx over 5% for 5 min, no healthy API task, the VM failing status checks (recovered automatically) | | `alarms_reach_the_alert_email` |
| The account's GitHub OIDC provider is looked up, not created | rad-shift's `github-oidc` stack made the account's only one | — |
| Availability zones named, not looked up | The set can't change under the stack | `two_availability_zones_exactly` |

Not yet: CloudFront signed cookies for the recordings (the random path is the
key, as locally), `terraform plan` in CI on pull requests (needs an AWS role
CI can use), and staging plus production as separate environments.
