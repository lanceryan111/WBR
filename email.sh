Hi Marcin,

Collected a few more details that may impact the estimate.

1. AT repo is already in TD Universe — release code will be manually SCP’d from DevX.
2. There’s no existing AT mobile pipeline to reuse, so we’d need to build a dedicated mobile CI pipeline.
3. Apple signing (Developer Portal / certs / P12) is currently under CMOB ownership, so moving off CMOB would introduce additional setup and coordination.

One additional consideration — mobile CI setup is quite different from a typical backend service pipeline. Besides CI orchestration itself, it also involves:

* macOS runner provisioning and machine lifecycle management
* Apple signing / certificates / provisioning profile management
* Mobile-specific build toolchains and environment dependencies (Xcode, Android SDK, Fastlane, etc.)

Because of these environment dependencies, the setup effort is usually more infrastructure-heavy than standard service CI.

Based on this:

• If we configure and host the AT Macs → ~4 weeks
• If we leverage CMOB runners → ~1–2 weeks for pipeline implementation

Given the timeline pressure, using CMOB runners feels like the faster option for now. Happy to discuss tomorrow.