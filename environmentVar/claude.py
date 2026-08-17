Both files parse cleanly.两个 workflow 都做好了并已经发给你：

**package-and-upload-config.yml**（放 wbr-app-config 仓库）— push 到 main 时自动检测哪个 app 文件夹的 config 变了，只把变化的那些打包（首次运行没有 diff 基准时会打包所有有 defaults.yml 的 app），
  每个 app 打成 `{app_name}-config.tar.gz`（含 defaults.yml + 所有 `*-config.yml`），用 `mvn deploy:deploy-file` 以 GAV 方式（groupId/artifactId=app_name/version）发到 Nexus，
也支持手动 dispatch 指定单个 app_name 或 version。

**download-and-deploy-config.yml**（放 ansible 那个仓库，比如 wbr-ghrunner-libs）— 手动触发，选 environment（dev/pat/drp/prod）+ app_name + 可选 version，
  用 `mvn dependency:copy` 从 Nexus 拉对应 GAV 的 tar.gz，解压后用 Python 脚本把 defaults.yml 和对应环境的 `{env}-config.yml` 深度合并，
  把 `ENV_VARS` 里的键（ENV/NAME）直接导出、`JVM_ARGS` 逗号拼接、`RUN_ARGS` 空格拼接，全部写进 `$GITHUB_ENV`，然后同一个 job 里跑 `ansible-playbook --tags deploy_app_scripts`，
  这样 group_vars 里 `lookup('env', 'JVM_ARGS')` 这类读取就能拿到新值，deploy_scripts.yml 的 template task 重新渲染 start_app.sh.j2/stop_app.sh.j2 时就带上了覆盖后的值。

有几处我是按合理假设写的占位符，文件里都标了 `TODO`，需要你确认/改一下：

- `GROUP_ID: com.wbr.appconfig` — 你们真实的 Nexus groupId 约定
- `runs-on: [self-hosted, wbr-ghrunner]` — 猜的 runner label，按你实际的 self-hosted runner 名字改
- `PLAYBOOK_PATH` / `INVENTORY_PATH` — 我按目录结构猜的路径，需要对照你实际的 playbook 入口和 inventory 位置改
- Secrets 用的是 `NEXUS_URL`/`NEXUS_USERNAME`/`NEXUS_PASSWORD`，以及已有的 `ANSIBLE_REMOTE_USER`/`ANSIBLE_BECOME_PASS`/`ANSIBLE_PASSWORD`（图5 group_vars 里已经在用）

另外，download-and-deploy-config.yml 文件末尾我补了一段注释，把你在图5第26-27行画的草稿补完整了（`environment_jvm_properties` 怎么从 `JVM_ARGS` 这个 env var 拆出 list），
因为 start_app.sh.j2 里 `environment_jvm_properties[application.name] | join(" ")` 需要这个字典结构才能生效——这部分需要你实际改到 group_vars 文件里,我这边没有权限直接改你仓库里的文件。

我重新读了一遍五张图，发现我第一版有几个地方想得不对。先确认两个关键点再改。确认了。用户选了保持 env vars 路线 + 一并改模板。Now let me verify everything actually works by rendering the template with the sample config from 
图1.Whitespace bug — my `{#-` comment tags are eating the preceding newline, so lines run together. Let me fix and retest under Ansible's actual Jinja defaults.Both render cleanly. Now shell-syntax check and verify the variables actually expand as intended.Let me verify the embedded Python blocks survive YAML block-scalar de-indentation — Python is indentation-sensitive and this is an easy place to introduce a break.重新想了一遍，我第一版有个根本性的问题：**两个 workflow 就算写得再干净也不会有任何效果。**

图2 里 start_app.sh.j2 的 13-17 行是写死的（`JAVA_HEAP_SIZE_MIN="2048m"`、`RUN_ARGS=""`），一个 Jinja 变量都没有。而你画的那段 `# >> CONFIGURATION <<`（24-30 行）在第 22 行 `exit "${EXIT_CODE}"` 之后 —— 是永远执行不到的死代码。所以模板本身根本不接任何外部值，管道再漂亮，渲染出来的脚本还是 2048m。这才是缺的那一环，我上一版只在文件末尾提了一句，权重给错了。

其他几处修正：

**JSON 编码而不是裸字符串。** 你在 DEV_GH.yml 26-27 行画的 `lookup('env', 'JVM_ARGS')` 路线保留了，但 workflow 导出的是 JSON，group_vars 用 `| from_json` 解回来。因为 JVM_ARGS 是 YAML list，裸 env var 会拍成字符串 `"['-Xms1024m', '-Xmx2048m']"`，模板里 `| join(' ')` 就变成逐字符遍历了。

**ENV_VARS 收进一个 `APP_ENV_VARS`。** 我上一版把 `ENV` 和 `NAME` 直接写进 `$GITHUB_ENV` —— 这是错的。这两个名字太通用，会污染 runner 的 shell 环境（`NAME` 尤其危险）；而且它们本来就是给目标机上 app 用的，应该由模板渲染成 export 行落到目标机，不是设在 CI 上。

**`LATEST` 换成读 maven-metadata.xml。** Maven 3 已经废弃了 `LATEST`/`RELEASE` 元版本，解析行为不可靠。`deploy:deploy-file` 本来就会写 maven-metadata.xml，直接读它更稳。

**Shell 注入。** 上一版把 `${{ inputs.app_name }}` 直接插进 shell，一个 `; rm -rf /` 就执行了。现在所有输入都走 `env:` 再用 `"$VAR"` 引用，actionlint 跑过无告警。

**环境找不到配置文件时硬失败。** 上一版缺 `prod-config.yml` 会静默退回只用 defaults 部署 —— 这种 bug 只会在凌晨的 prod 上被发现。

验证做了：两个 workflow 过 actionlint（只剩 `wbr-ghrunner` 这个自定义 label 未知的预期告警）；内嵌的 Python 块确认经过 YAML block scalar 缩进剥离后仍能 parse；模板按 Ansible 真实的 Jinja 默认值（trim_blocks=true、lstrip_blocks=false）渲染过两种情况 —— 注入配置时出 `-Xms1024m -Xmx2048m` / `RUN_ARGS="D"` / `export ENV="dev"`，不注入时正确退回你原来的 2048m 和空 RUN_ARGS；渲染结果过 `sh -n`，并实际跑了一遍确认变量展开正确。第一次渲染时发现 `{#-` 把前面的换行吃掉导致行粘连，已修。

另外两个顺带发现的，写在 group_vars_snippet.yml 末尾：

- deploy_scripts.yml 第 9 行 `"{{ 'yes' if config_environment == 'local' else 'no' | bool }}"` —— `| bool` 只绑定到 `'no'`，不是整个三元表达式，实际返回字符串 `'yes'` 或布尔 `False`。现在能work纯属 Ansible 把 `'yes'` 强转成了 true。要加括号。
- 变量命名三套并存：deploy_scripts.yml 用 `app_name`，模板用 `deploy_app_details.name`，你的草稿用 `application.name`。`application` 在别处没出现过，我按 `deploy_app_details.name` 写的。

**关于 start_app.sh.j2 有个重要提醒**：照片里 5、8、15、19、27-30 行右边被截断了，我标了 `RECONSTRUCTED` 的行是我推测补的，尤其是 `-XX:` 那串尾巴和 `su` 那行的重定向部分，提交前一定要跟真实文件 diff 一下。还有你草稿第 30 行把 `>>` 日志重定向塞进 `RUN_ARGS`，但第 19 行的 `su` 里已经有重定向了，我没搬过来 —— 两边都放会重复输出，你确认下想放哪边。
