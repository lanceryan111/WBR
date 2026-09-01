You're right on both counts. Let me look at what that existing step actually tells me, because it changes more than the job count.Only the expected custom-label findings. The riskiest new construct is a heredoc nested inside an `if !` inside a `for` loop — let me actually execute that logic against a real fixture.The loop behaves correctly, but there's a cosmetic bug: broken-app prints an error *and* an "ok" line. Let me fix that and verify the round-trip into the deploy side.**两个 job 是我过度设计了。** 唯一的技术理由是 GitHub Actions 的 matrix 必须在 job 启动前就确定，没法在同一个 job 里算出来，所以动态 matrix 强制要拆两个 job。但你现在实际就一个 app，打包的是几个几 KB 的 YAML —— 为此付出第二次 checkout、job 之间 JSON 传值、self-hosted runner 上多排一次队，完全不划算。已经改成单 job 里一个 `for` 循环。唯一损失的是 UI 里没有每个 app 独立的成功/失败格子，我用 `::group::` 分组 + 最后统一汇总失败列表补上了：一个 app 挂了不会中断其他的，但最后整体 exit 1。

**更重要的是，你那张图推翻了我一个基础假设。** 你之前选的是「Maven-hosted (GAV坐标)」，但图里第 166 行写的是 `repository=application-managed-raw-3rd-party`，`INPUT_FUNCTION: "upload_raw_artifact_nexus"` —— 你们实际用的是 **raw 仓库**，不是 maven-hosted。这不是小差别：

- GAV 坐标、`mvn deploy:deploy-file`、settings.xml 全部不需要了，改用你现有的 `main.py` + 那套 env 契约
- 上一版 deploy workflow 靠读 `maven-metadata.xml` 来解析「最新版本」—— **raw 仓库根本没有这个文件**，那段代码在你们环境里必然失败。所以 `config_version` 现在是必填输入，跟你 ghrunner-libs 那个 workflow 用 `inputs.version` 的习惯一致，部署时锁定配置版本本来也更稳妥
- 下载改成直接 `curl` 打 raw 路径 `{host}/repository/{repo}/{dir}/{app}/{app}-{version}.tar.gz`，不需要任何 helper。如果 `main.py` 里有 `download_raw_artifact_nexus` 之类的对应函数，可以换成那个更统一

上传步骤完全照搬你的 env 契约，只是循环里改成每次迭代前置赋值：

```
INPUT_FUNCTION="upload_raw_artifact_nexus" \
NEXUS_ASSET_FILENAME="${app}-${VERSION}.tar.gz" \
NEXUS_DIRECTORY_PATH="${NEXUS_DIRECTORY_ROOT}/${app}" \
LOCAL_UPLOAD_FILEPATH="$tarball" \
... python3 wbr-ghrunner-libs/wbr_actions/main.py
```

验证：造了一个正常 app + 一个 `JVM_ARGS` 写成字符串的坏 app，实跑了整个循环（用 stub main.py 断言 env 契约和 tarball 真的存在）—— 正常的打包上传成功，坏的被 shape check 拦下、循环继续、最后 exit 1。然后把产出的 tarball 直接喂进 deploy 的 merge 逻辑，确认 `dev-config.yml` 正确覆盖 `defaults.yml`（512m → 1024m/2048m，ENV unset → dev）。也验证了缺 `prod-config.yml` 时是硬失败而不是静默按 defaults 部署。顺带修了个验证输出的小 bug：坏文件会同时打印 error 和 ok。

有两个需要你确认的（文件里标了 TODO）：

1. **`NEXUS_DIRECTORY_ROOT`** 我按你 libs 的 `W000WBR/Libraries/wbr-ghrunner-libs` 的形状猜了个 `W000WBR/AppConfig`,这个得问你们 Nexus 那边的约定。
2. **`main.py` 的跨仓库 checkout** —— 它在 wbr-ghrunner-libs 里，而这个 workflow 跑在 wbr-app-config 里，所以我加了一步 checkout 那个仓库。私有仓库跨库 checkout 用不了默认的 `GITHUB_TOKEN`,需要一个 PAT。如果你们 self-hosted runner 上本来就有 main.py，那这步可以直接删掉更省事。

start_app.sh.j2 和 group_vars_snippet.yml 跟 Nexus 换不换仓库类型无关，上一版的还能用，没重发。

这个方向对，shell 堆在 workflow 里确实难维护也没法单独测。我按 `upload_raw_artifact_nexus.py` 的约定（一文件一函数、函数无参、全部走 `os.getenv`）拆一下。Now the workflows become thin dispatch calls.Only the expected label warnings. Now a real end-to-end run of the modules, including serving a fake Nexus over HTTP so the download path is actually exercised.`$?` there was grep's, not Python's. Let me check the real exit code and continue the chain.全部 shell 逻辑搬进 `wbr_actions/` 了，5 个模块，严格按 `upload_raw_artifact_nexus.py` 的约定：文件名 = 函数名、函数无参、输入全走 `os.getenv`、`logging.basicConfig(level=logging.DEBUG)`。

| 模块 | 干什么 | 用在哪 |
|---|---|---|
| `package_app_config` | 检测变更的 app → 校验 YAML → 打 flat tar.gz | wbr-app-config |
| `upload_app_config` | 逐个推到 raw Nexus | wbr-app-config |
| `download_app_config` | 按版本拉取 + 解压 | wbr-ghrunner-libs |
| `merge_app_config` | defaults + env config 合并 → JSON 写进 GITHUB_ENV | wbr-ghrunner-libs |
| `run_ansible_deploy` | 拼参数跑 ansible-playbook | wbr-ghrunner-libs |

workflow 现在每步就是 `python3 wbr_actions/main.py` + 一个 `env:` 块，跟你现有 upload step 长得一模一样。

`upload_app_config` 是复用你现有那条链路的：同样 `from wbr_util import gh_nexus_rest_api`，同样 `upload_nexus_artifact(url, payload, files)`，同样的 payload/files 结构，只是多 app 循环 + 每个 app 算自己的 directory。我加了个 `with open(...)` 包住文件句柄 —— 你原来那个是裸 `open()`,单次调用没问题，但循环里一旦中途失败会漏 fd。

**验证做了完整链路实跑**：造了一个正常 app + 一个 `JVM_ARGS` 写成字符串的坏 app，用 stub 的 `gh_nexus_rest_api` 和一个动态 import 的 `main.py` 跑完 package → upload → download → merge。download 那步是**起了个真的 HTTP server 当假 Nexus**,所以 URL 拼接和 404 处理都是真跑出来的，不是纸上推演。确认：坏 app 被拦下且退出码 1、好 app 正常走完、`dev-config.yml` 正确覆盖 `defaults.yml`（512m→1024m/2048m，ENV unset→dev，defaults 里独有的 REGION 保留）、缺 `prod-config.yml` 硬失败、拉不存在的版本报清晰的 404。最后把 `GITHUB_ENV` 的值喂进 `start_app.sh.j2` 渲染，确认 `export ENV="dev"` / `JAVA_OPTS` / `RUN_ARGS="D"` 都对。

三件需要你确认的：

1. **`main.py` 的分发方式。** 我不知道它是动态 import 还是硬编码注册表。如果是动态 import（`importlib.import_module(fn)` 然后 `getattr(mod, fn)()`），这 5 个直接就能用；如果是硬编码的 dict，要把新函数名加进去。
2. **`requirements.txt`** 需要有 `PyYAML` 和 `requests`。`requests` 大概率已经有了（`gh_nexus_rest_api` 应该在用），`PyYAML` 不一定。
3. **`NEXUS_DIRECTORY_ROOT`** 我按你 libs 的 `W000WBR/Libraries/wbr-ghrunner-libs` 猜了个 `W000WBR/AppConfig`,得跟 Nexus 那边对一下。

另外 `download_app_config` 我用的是 `requests` 直接 GET，因为 raw 仓库就是固定路径的文件，不需要 helper。如果 `wbr_util` 里其实有下载的对应函数，换成那个更统一 —— 我看不到 `wbr_util` 的完整 API，只能从你截图里的 `upload_nexus_artifact` 推。
