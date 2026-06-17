Hi Derek,

Ahead of the discussion, I wanted to share a quick overview of our current branching approach.

We maintain a default baseline branch as the source branch. Each release branch is created from this baseline, and developers create feature branches from the target release branch for development.

When a feature is ready, merging into the release/default branch triggers a CI validation build. If validation passes, code is merged and the release/default branch build generates a release candidate artifact, which is uploaded to Nexus.

This approach keeps release branches aligned, reduces divergence, and enables a consistent CI/CD process.

Thanks,
Fei