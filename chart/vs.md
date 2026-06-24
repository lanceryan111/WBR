```markdown
## Trade-offs

This document uses a **cascading merge** strategy. The most common alternative is a **mainline-development + manual cherry-pick** model. The key difference is *which branch is the stable one* and *how fixes propagate*.

### Cascading Merge (this strategy)

`master` is the stable mainline. Release branches are cut from `master`, development happens on the release branches, and any fix merged into the oldest release is automatically propagated forward through cascade PRs — release by release — until it reaches `master`.

**Pros**

- **Automatic propagation, no missed fixes** — the biggest advantage. Once a bugfix lands in a release, every newer release and `master` receive it automatically, making "a release missed the fix" regressions nearly impossible.
- **Less human error** — engineers don't have to remember which branches a fix needs to reach.
- **Auditable** — each propagation is a PR: recorded, reviewable, and gateable by CI.
- **Always-stable `master`** — a new release can be cut from `master` at any time.

**Cons**

- **Cascade conflicts stall the pipeline** — if a cascade PR for an intermediate release conflicts, the whole chain halts until it's resolved manually, and conflicts tend to pile up the further down the chain they occur.
- **Tight coupling** — release branches are bound together by the automation chain, so a problem in one branch blocks everything downstream.
- **Infrastructure cost** — requires maintaining automation (`cascading.py`), CI integration, and guard logic.
- **Fixed direction** — propagation only flows old → new; selectively landing a fix in some releases but not others is awkward.

### Mainline Development + Manual Cherry-pick (alternative)

`master` is the active development line. At release time, code is cut into a stable release branch that is then frozen and rarely changed. When QA finds a bug, the fix is made on the release branch, and a developer must **manually cherry-pick** it back to `master` and to any future release branches.

**Pros**

- **Isolated, stable release branches** — once frozen, a release branch only accepts explicit, approved fixes, making release quality controlled and predictable.
- **Precise, controlled propagation** — cherry-pick is an explicit choice, so you can decide exactly which branches each fix lands in. Ideal for selective backports.
- **Decoupled branches** — release branches are independent; a conflict in one never blocks the others.
- **Industry-standard model** — most teams are familiar with it (a release variant of git-flow / GitHub flow), so onboarding is cheap and no custom automation is required.

**Cons**

- **Easy to miss a cherry-pick** — the biggest risk. Relying on memory and discipline, fixes often land in a release but get forgotten on `master` or some future release, causing **regressions** (a fixed bug reappears in a newer version).
- **Repetitive and error-prone** — the same fix must be applied manually to multiple targets, and cherry-picks can introduce differences from the original fix.
- **Hard to audit** — answering "which branches did this fix reach?" requires manual investigation, with no guarantee of consistency.
- **Scales poorly** — the more releases you maintain, the more cherry-pick targets there are, and the heavier the burden grows.

### Summary

| Dimension | Cascading Merge (this strategy) | Mainline + Cherry-pick |
|---|---|---|
| Stable branch | `master` | release branch |
| Fix propagation | automatic, forward cascade | manual, explicit cherry-pick |
| Risk of missed fixes | low | high |
| Precise propagation control | weak | strong |
| Branch coupling | high (chain can stall) | low |
| Infrastructure cost | high (needs automation) | low |
| Onboarding difficulty | higher | low (industry-standard) |

**Rule of thumb:** if you maintain many releases and your main fear is regressions from missed fixes, cascading merge wins. If release branches must be strictly frozen, fixes need selective backporting, and you'd rather not maintain automation, mainline + cherry-pick wins.
```

The outer fences are just for display here — paste the inner content as a new `## Trade-offs` section in `CASCADING_MERGE_STRATEGY.md`. Want me to merge this with the earlier `## Algorithm` block into one complete file you can drop in?