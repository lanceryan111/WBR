Hi Marcin,

**Current situation**

QS has K8s (1 JVM), Dev (2 JVMs), and SIT (2 JVMs), but only Dev is currently used. Dev receives ongoing feature deployments while also serving release-testing needs. This creates a moving test baseline: new changes can interrupt validation, complicate defect reproduction, and make release readiness difficult to confirm. The existing environments are not yet being used to separate development from release stabilization.

**Target state**

- **Dev:** Continuous feature development and testing.
- **SIT:** Approved, initially tested release candidates for integration/regression testing before PAT/production.
- **Production Support (potential):** Production-aligned baseline for incident reproduction and hotfix validation.

**Technical proposal**

- **Environment isolation:** Assign existing infrastructure to these roles. Separate deployment targets, configuration, secrets, and stateful dependencies so Dev activity cannot disrupt SIT.
- **Branch strategy:** `feature/*` → PR → `main` → automatic Dev deployment. Cut `release/<version>` from an agreed baseline for SIT; accept only release fixes while development continues on `main`. Exclude incomplete features or disable them with feature flags.
- **Code maintenance:** Require PR reviews and CI checks. Carry release fixes into `main`. Create hotfixes from the deployed production tag and incorporate them into `main` and affected release branches.
- **Release control:** Pin microservice artifact versions in a release manifest, gate SIT deployments, and promote the same validated artifacts to PAT/production with environment-specific configuration.

**Next step:** Confirm environment mapping, capacity, and ownership, then pilot Dev/SIT separation for one release. Assess a dedicated production support environment afterward.

Thanks,
