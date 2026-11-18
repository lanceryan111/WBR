# Known issues (agent-facing — newest first, ≤ 8 lines each)

<!-- Template — copy for each entry:
## YYYY-MM-DD — <short title>
- **Symptom:** exact error string / signal (so it can be grepped)
- **Where:** service / env / workflow
- **Root cause:** one or two lines
- **Fix:** what changed (file/PR)
- **Verify:** command that proves it's fixed
-->

## 2026-10-01 — Example: orders-svc OOMKilled after JDK upgrade
- **Symptom:** `OOMKilled`, exit 137, restarts every ~20 min
- **Where:** orders-svc, dev
- **Root cause:** `-Xmx2g` hardcoded while limit was 2Gi; no room for metaspace/threads
- **Fix:** removed `-Xmx`, set `JAVA_TOOL_OPTIONS=-XX:MaxRAMPercentage=75` (helm/orders/values.yaml)
- **Verify:** `kubectl -n dev get pod -l app=orders-svc` restarts stay 0 for 24h
