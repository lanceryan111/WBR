可以发给 Marcin：

Hi Marcin, regarding the branch strategy for the AT project — after looking into their current setup, it seems the repo wasn’t originally structured following TD’s standard branching model. Instead of maintaining a default baseline branch and promoting changes forward, each release imports a new release branch, which has caused branches to diverge over time.

As a result, developers often need to branch off multiple feature branches for different release lines for the same feature, and the current WBR branch strategy is difficult to apply directly.

Do we want to use this opportunity to drive alignment toward the TD standard branch strategy, or should we adapt the CI solution to support their existing release model?

如果想再短一点、更像 Teams message：

Hi Marcin — quick observation on AT branch strategy: their project wasn’t set up following TD standards initially. They create/import a new release branch each cycle instead of maintaining a default baseline branch, so branches have diverged over time. Developers now often need separate feature branches per release line. In the current state, WBR’s branch strategy is difficult to apply directly. Do we want to push for alignment to TD standards, or support the existing model for now?