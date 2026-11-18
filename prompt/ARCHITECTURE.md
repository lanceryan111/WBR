# Architecture (agent-facing — keep under ~150 lines, facts only)
<!-- Generated with /bootstrap-knowledge, then reviewed by a human. Cite source paths. Mark guesses with (inferred). -->

## Services
| Service | Module path | Purpose | Talks to | Data stores | Owner |
|---|---|---|---|---|---|
| orders-svc | services/orders | ... | payments-svc (REST), Kafka `orders.*` | Postgres `orders` | team-x |

## Environments
| Env | Cluster / context | Namespace(s) | Helm release | Values file | Deployed by |
|---|---|---|---|---|---|
| dev | ... | ... | orders | helm/orders/values-dev.yaml | GH Actions `deploy.yml` on merge to main |
| prod | ... | ... | orders | helm/orders/values-prod.yaml (change-controlled) | manual approval |

## Request / deploy flow
1. PR → `ci.yml` (build, test, image scan)
2. merge → image pushed to `<registry>` with tag `<sha>`
3. `deploy.yml` → `helm upgrade` per env
4. Hosts outside K8s (VMs, DB proxies, ...) configured by Ansible: `ansible/site.yml`

## Configuration
- Spring profiles: `dev`, `prod`, ... — set via `SPRING_PROFILES_ACTIVE` in Helm values
- Secrets: <ExternalSecrets / Vault / sealed-secrets> — names, not values
- TLS / keystores: where they're mounted, which env vars point at them (names only)

## Cross-cutting conventions
- Health: `/actuator/health/{liveness,readiness}`; metrics `/actuator/prometheus`
- Logging: JSON, field `traceId`
- Timeouts / retries: ...

## Gotchas
- (things that surprised people — link to KNOWN_ISSUES entries)
