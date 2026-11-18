# Repo map (agent-facing — one line per entry)
<!-- Generated from repo-facts.sh. Update when directories move. -->

| Path | What it is | Entry point / key files |
|---|---|---|
| `services/orders/` | orders-svc Spring Boot app | `OrdersApplication.java`, `src/main/resources/application.yml` |
| `libs/common/` | shared library | ... |
| `helm/orders/` | Helm chart for orders-svc | `values.yaml`, `values-dev.yaml`, `values-prod.yaml` |
| `ansible/` | host configuration | `site.yml`, `inventories/{dev,prod}`, `roles/` |
| `.github/workflows/` | CI/CD | `ci.yml` (PR), `deploy.yml` (merge) |
| `docs/ai/` | agent knowledge pack | this file, ARCHITECTURE.md, KNOWN_ISSUES.md |

## Where to look for…
- A REST endpoint → `services/*/src/main/java/**/web/*Controller.java`
- A config property → `application*.yml`, then Helm `values-<env>.yaml` `env:` section (use `/trace`)
- Why a deploy failed → `deploy.yml` run logs (skill: ci-failure-triage)
- Whether the cluster matches the repo → skill: config-drift
