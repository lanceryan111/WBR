我把 11 张截图里的 workflow 完整重建后逐行 review 了一遍，重构版文件已发给你（修复点都写在注释里）。下面是 review 结论，按严重程度排列。

## 一、会直接导致错误行为的 bug

**1. `publish` job 的 `needs.build` 引用是空的（最严重）**
`publish` 只声明了 `needs: [resign]`，但里面引用了 `needs.build.outputs.additional_params` 和 `needs.build.outputs.BASELINE_COMMIT`。GitHub Actions 的 `needs` 上下文只包含直接列出的 job，所以这两个值**永远是空字符串**——`./gradlew  publish` 实际没带任何参数，release notes 的 commit 范围也拿不到。修复：`needs: [build, resign]`。

**2. 测试报告 artifact 名字在 matrix 两个 leg 冲突**
`upload-artifact@v4` 不允许同一个 run 里上传两个同名 artifact。`tests_reports_UnitTestPlan` 在 Sim 和 Device 两个 leg 都会上传，后到的那个必然报 409 失败。而且 coverage 跟 platform 无关，跑两遍纯属浪费一台 macOS runner 的时间。修复：coverage + 上传只在 `matrix.platform == 'Sim'` 时执行，一箭双雕。

**3. `inputs.target_branch` 不存在**
`baseBranchName: origin/${{ inputs.target_branch }}` —— 但 `workflow_dispatch` 只声明了 `disable_build_cache`，这个值永远是 `origin/`，疑似从 release workflow 复制来的残留。要么声明该 input，要么删掉。

**4. concurrency 缺 `cancel-in-progress: true`**
第 26 行注释写着"Cancel workflow runs in progress"，但 `concurrency` 块里只有 `group`，默认行为是**排队**而不是取消。注释和行为不一致，加上 `cancel-in-progress: true` 才是注释描述的效果。

**5. "Find Last Successful Commit" 疑似缺 `id`**
job outputs 引用了 `steps.find-baseline-commit.outputs.BASELINE_COMMIT`，但截图里该 step 没看到 `id: find-baseline-commit`。如果确实没有，这个 output 永远为空（和 bug 1 叠加，双重保证了 `GIT_PREVIOUS_SUCCESSFUL_COMMIT` 是空的）。请对照原文件确认。

**6. 分支校验正则有漏洞**
`^(refs/heads\/)?(master|project|concept)\/*` 里 `\/*` 是"0 个或多个斜杠"，且末尾没有锚定，所以 `conceptual-x`、`masterpiece` 这类分支都能通过校验。应改为 `^refs/heads/(master$|project/|concept/)`。

## 二、幂等性问题（重跑/脏工作区场景）

**7. unzip 不可重入。** 自托管 runner 的工作区不会自动清理，`unzip x.zip -d dir` 在目标文件已存在时会进入交互式询问（CI 里表现为挂死）或失败。改为先 `rm -rf` 目标目录再 `unzip -oq`，并在 `checkout` 上加 `clean: true`，保证每次 run 从干净状态开始。

**8. `find dist -name '*.ipa' | head -n 1` 顺序不确定。** `find` 的输出顺序依赖文件系统，脏工作区里残留多个 ipa 时选到哪个是随机的。加 `sort` 保证确定性（`clean: true` 之后风险也降低了）。

**9. 发布版本号 = `run_number`。** re-run 同一个 run 时 run_number 不变，这对幂等是好事——但前提是 Nexus 端对"版本已存在"做覆盖或 skip，否则 re-run publish 会 409。建议在 gradle publish 任务里加存在性检查。

**10. matrix job 的 outputs 是"最后写完的 leg 获胜"。** 目前四个 output 恰好在两个 leg 上取值相同所以没炸，但这是踩在钢丝上的正确。长期建议把 `setup-publishing` / `setup-vars` / `find-baseline-commit` 拆成一个独立的 `setup` job，matrix build 消费它的 outputs——算一次、语义明确、还能省 runner 时间。

## 三、安全与工程设计

**11. 脚本注入面。** 多处把 `${{ github.ref_name }}`、`${{ steps.*.outputs.* }}` 直接内联进 `run:` 脚本。分支名可以包含 `$`、`;`、引号等字符，属于典型的 script injection 向量（GitHub 官方 hardening 指南明确点名）。全部改为经 `env:` 传入再在脚本里用 `"$VAR"` 引用。

**12. 权限过宽。** workflow 级别的 `contents: write` + `pull-requests: write` 被所有 job（含第三方 action）继承。这个流程里 build/resign/publish 其实只需要 `contents: read`；写权限应下放到唯一需要的 `ios_sonar_check`。

**13. Action pin 在功能分支上。** `signing-service@feature/SERPOMF-41036-Signing-Service` 是可变引用，随时可能被 force-push 或分支删除，构建不可复现也不可审计。合并后应 pin 到 tag，最好是 commit SHA。

**14. 环境硬编码。** `PATH` 写死了 `/Users/ciusr/.rbenv/...`，`JAVA_HOME` 写死了具体 JDK 小版本，仓库名在 baseline-commit 命令里写死——这些把 workflow 焊死在特定 runner 镜像上。PATH/JAVA_HOME 建议移到 runner 镜像或受版本管理的 setup 脚本，仓库名用 `${{ github.repository }}`。

**15. 死代码若干。** 注释掉的 nightly cron（需要的话建议单独建 nightly workflow 通过 `workflow_call` 复用）；`setup-vars` 里的 `pull_request` 分支判断和 sonar 的 `github.head_ref ||`（本 workflow 根本没有 PR 触发器，永远走不到）；注释里的 "conccept" 拼写错误。另外 `sonar_project_key` 末尾的冒号看起来可疑，值得确认。

**16. 缺 `timeout-minutes`。** 自托管 macOS 上 xcodebuild/fastlane 偶发挂死，没有超时就会占着 runner 直到 6 小时默认上限。每个 job 都该设。

**17. 两个 job 的大段 env 重复。** build 和 publish 各维护一份相同的 PATH/JAVA_HOME/fastlane 配置，提到 workflow 级 `env:` 一处维护。

优先落地顺序建议：先修 1、2、4、5（这几个当前每次 run 都在产生错误结果或必然失败的隐患），再做 7 的幂等改造，其余按节奏排。重构文件里凡是截图被截断看不清的地方我都标了 `TODO(verify)`，合并前请对照原文件补齐那几行。

先说结论：这份 Android 版（TDWARTSE-14983 的 refactor）比 iOS 版明显干净——`needs: [build, sign]` 是对的、artifact 名字带 matrix 后缀不冲突、大部分脚本走了 `env:` 传参。但 iOS review 里的几个通病仍然原样存在，而你点名的 Stage/Restore 两大段 shell 有一个结构性问题。重构文件已发给你，下面是分析。

## 一、Stage unsigned APKs / Restore signed APKs（重点）

**核心问题：同一份「逻辑名 ↔ gradle 输出路径」的知识散落在 4 个地方**——Stage 的 6 行 `cp`、sign job 手写的 6 项 matrix、Restore 的 6 行 `mkdir` + 6 行 `cp`、还有 assemble 的 gradle task 清单。将来加一个 flavor 要同步改 4 处，漏一处就是静默发布错误制品。此外 `versionName` 从 `gradle.properties` 用 awk 解析了**两遍**（build 和 publish 各一遍），解析逻辑对 `versionName = 1.2.3` 这种带空格的写法也是脆的。

**重构方案（已写进文件）**：Stage 时生成一份 `manifest.tsv`（逻辑名 TAB 相对路径，versionName 在此刻解析一次并直接代入路径），随 unsigned-apks artifact 一起上传。之后：

1. Stage 变成一个循环——逐行读 manifest 复制，并且**校验源文件存在**（原来的 `cp` 靠 bash -e 报错，报的是 cp 的错误信息而不是"这次构建没产出这个 APK"）。
2. Restore 变成 manifest 的**反向循环**——`mkdir -p "$(dirname "$dest")"` 替代手写 6 个目录，publish job 完全不再碰 `gradle.properties`。
3. sign 的 matrix 改为 `fromJSON(needs.build.outputs.artifact_list)` 动态生成，从 manifest 派生。

改完之后加减 flavor 只改 manifest 一处（gradle task 清单是唯一保留的第二份，因为 task 名没法机械推导——注释里建议在 gradle 侧加一个聚合 task 彻底收敛）。

**幂等性问题（这两段的另一半风险）**：自托管 runner 的 `app/build/` 跨 run 残留。两个具体场景：

在 build job 里，如果某个 assemble task 这次没产出（或 task 清单以后改了），`cp` 会把**上一次 run 的旧 APK**照常复制上传——签名、发布，全程无人察觉。在 publish job 里更危险：`-Ptd.skipPublicationBuild=true` 意味着 gradle 直接发布 outputs 目录里的现成文件，而 restore 之前没有清理，目录里可能躺着上次 run 的（甚至未签名的）残留。修复：两个 job 都在关键步骤前 `rm -rf app/build/outputs/apk`（精确清理，不用 `checkout clean: true`——那会 `git clean -ffdx` 连 gradle 增量缓存一起清掉，牺牲自托管的构建速度）；`unsigned-apks/`、`signed-apks/` 同理先删再建，否则 flavor 清单缩减后 wildcard 上传会带上陈旧文件。

## 二、从 iOS 版原样延续的问题

**1. concurrency 仍缺 `cancel-in-progress: true`** —— 第 24 行注释说取消，实际排队。

**2. workflow 级权限仍过宽**（`contents: write` + `pull-requests: write`），改为顶层 `contents: read`，写权限只留给 sonar_check。

**3. signing-service 仍 pin 在 `feature/SERPOMF-41036` 功能分支** —— 可变引用，不可复现不可审计。

**4. 分支校验被整段注释掉了（46-52 行）** —— 这里比 iOS 版后果更重：`workflow_dispatch` 可从**任意分支**触发，而非 project/concept 分支的 `ARTIFACT_SUFFIX` 是空串，publish 会以和 master 完全相同的 Nexus 坐标发布制品，直接污染主线。建议恢复校验（我在重构版里用修正后的正则恢复了，原正则的 `\/*` 漏洞同 iOS review 第 6 条）。

**5. 缺 `timeout-minutes`、环境硬编码 `/Users/ciusr`、仓库名写死、`BUILD_NUMBER = run_number` 的 re-run 发布语义** —— 同 iOS review，不再展开。

## 三、本文件特有的其他发现

**6. `ADDITIONAL_PARAMS` 逻辑写了两遍**（build 的 Configure 步骤 + publish 的 Publish 步骤内联重复），且 build 里是写 `GITHUB_ENV` 再用 `${{ env.ADDITIONAL_PARAMS }}` 内联进脚本——改为 job output 一处计算、两处消费。

**7. iOS 和 Android 的 suffix 提取规则不一致**：iOS 用 `sed 's/.*\///'`（最后一段），Android 用 `cut -d/ -f2`（第二段）。`project/team/xyz` 这种分支在两个平台会得到**不同的 Nexus 后缀**。建议统一（重构版用了 `${BRANCH_NAME##*/}`，与 iOS 对齐；你们定哪个语义都行，但要一致）。

**8. Archive Test Reports 上传海量编译产物**：path 里包含 `javac/**`、`kotlin-classes/**`、`build/classes/**` 等数千个小文件（给 Sonar 用的）。`upload-artifact` 逐文件上传，这是每次 run 的显著耗时点——先 `tar` 成单文件再上传通常快一个量级。另外 `if: ${{ always() }}` 建议改 `!cancelled()`，手动取消时不再占着 runner 传大包。

**9. Get Baseline Commit 把 token 以 `'${{ github.token }}'` 内联进命令行** —— 自托管机器上进程参数对同机其他进程可见，改走 env。

**10. Ruby 3.1.6 写死了两处**（`RBENV_VERSION` env + `ruby -e 'abort ...'` 检查），检查脚本改为读 `$RBENV_VERSION`，单一来源。

**11. 小项**：build job 叫 "Initialize" 名不副实（它构建+测试+暂存）；`checkout ref: ${{ github.sha }}` 是默认值可删；`sonar_project_key` 末尾冒号同 iOS 一样可疑；6 个 sign matrix leg 各占一台 macOS runner 只为调一次签名服务——如果签名是远程调用，收敛成单 job 循环 6 次能省下 5 台 runner 的排队时间，值得权衡。

**12. 一点长期设计建议**：整个「build → 外部签名 → 把签名产物伪装回 gradle 输出路径 → `skipPublicationBuild` 发布」是在绕 gradle。更干净的做法是让 publish task 直接接受一个显式目录参数（如 `-Ptd.signedApkDir=signed-apks`），发布逻辑读那里——restore 步骤整个消失，也不再依赖「outputs 目录状态正确」这个隐含前提。这需要动 gradle 脚本，可以作为下一步。

落地优先级：先修 1、4 和幂等清理（这三个当前有真实的错误发布风险），再做 manifest 重构（消重复、防未来事故），其余按节奏。重构文件里截图看不清的位置同样标了 `TODO(verify)`。
