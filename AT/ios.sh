我先看一下相关的 skill,然后基于你图里的内容生成骨架文件。

这些是 YAML workflow 文件,直接生成即可,不需要文档 skill。

基于你图里的内容,我帮你搭一套 caller + reusable 的骨架。结构是:一个 caller workflow 做前期处理(sanitize、算 branch 变量、取 secrets),然后根据 develop / master / release 分流到对应的 build。我把每个 build 留成空壳,你往里填具体步骤。

Now the three reusable build workflows. They share the same input contract so the caller can hand them off uniformly. I'll create a reusable skeleton and stamp out develop/master/release.

Let me validate all four files parse as valid YAML before handing them over.

四个文件都通过了 YAML 校验。

四个文件都已生成,放在 `.github/workflows/` 下:

**`branch-build.yml`** — caller，是整套的入口。`init` job 做所有共享的前期处理(sanitize inputs、算 branch 分类、取 Vault secrets),把结果作为 outputs 暴露。关键是 `build_type` 这个 output,它把 branch 名归一成 `develop` / `master` / `release` 三类,下面三个 build job 各自用 `if: needs.init.outputs.build_type == '...'` 来决定是否触发。

**`develop-build.yml` / `master-build.yml` / `release-build.yml`** — 三个 reusable workflow(`workflow_call` 触发),共享同一套输入契约(`disable_build_cache` / `artifact_suffix` / `target_branch`),所以 caller 用统一的方式分发。每个里面我只放了 `Configure Additional Gradle Params` 和 `checkout` 做骨架,真正的 build 步骤标了 `# TODO` 等你填。

几个需要你确认/调整的点:

- **release 分支后缀解析**:我用的是 `cut -d/ -f 3`(对应 `releases/M/M13` → `M13`)。你图里 `branch-build.yml` 第 87 行原本是 `cut -d/ -f 2`,对应的是 `project/concept` 那类两段式分支。你的 release 是几段式要核对一下。
- **release 与 master 的差异**:目前我只在 release 里设了 `-Ptd.release=true`,develop/master 是 `false`。如果 master 也算 release 构建,把那行挪过去即可。
- **secrets 传递**:caller 用了 `secrets: inherit`,子 workflow 就能直接拿到。如果你想显式声明,我可以改成在每个 reusable 里写 `secrets:` 块。
- 我没把你原来的 `publish.yml` 纳进来。如果三种 build 最后都要走 publish,可以让每个 build workflow 末尾再 `uses: ./.github/workflows/publish.yml`,或者保持你现在 `needs: [init]` 直接 call publish 的方式。你想怎么接,我可以帮你串起来。