这个版本更像发给经理的 Teams，短一点但保留 reasoning：

Hi Marcin,

Collected a few more details that may impact the estimate:

1. AT repo is already in TD Universe — release code will be manually SCP’d from DevX.
2. There’s no existing AT mobile pipeline to reuse, so we’d need to build a dedicated mobile CI pipeline.
3. Apple signing (Developer Portal / certs / P12) is currently under CMOB ownership, so moving off CMOB would introduce additional setup and coordination.

Based on this:

• If we configure and host the AT Macs → ~4 weeks (env + dependencies + certs/secrets + CI setup)
• If we leverage CMOB runners → ~1–2 weeks for pipeline implementation

Given the timeline pressure, using CMOB runners feels like the faster option for now. Happy to discuss tomorrow.

这个版本更像 senior 的 update：facts → impact → recommendation。