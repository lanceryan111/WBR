Subject: Quick Touchpoint – AT Branch Strategy Alignment

Hi Derek, Gilbert,

We’d like to schedule a quick touchpoint to align on AT’s branching strategy.

Currently, AT does not follow the standard TD branching model. Instead of maintaining a baseline/default branch, each release introduces a separate release branch, which has led to branch divergence over time.

Key concerns with the current model:

* Developers may need to maintain the same feature across multiple release branches.
* Increased merge/conflict effort and reduced release consistency.
* Higher CI/CD complexity and limited applicability of existing WBR standards and automation.
* Increased long-term maintenance overhead.

The goal is to align on whether AT should move toward the TD standard model or whether the CI solution should adapt to the current approach.

Thanks,
Fei