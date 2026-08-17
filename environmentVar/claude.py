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
