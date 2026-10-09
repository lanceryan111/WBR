Thanks for looking into this, Sang Jun.

Based on what we’ve identified so far, there seem to be two areas that need to be addressed:

1. The automated version bump is causing CI to be skipped when merging between release branches.
2. The merge workflow is being triggered during the PR phase when it shouldn’t be.

The hanging required checks could be related to these behaviors, so I think we have a good starting point for troubleshooting.

Could you please take the lead on investigating and fixing these issues, including validating whether the required checks are properly triggered after the changes?

If you run into any blockers, feel free to share the details here so we can work through them together.