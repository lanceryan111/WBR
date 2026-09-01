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

