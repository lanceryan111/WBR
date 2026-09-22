这次改动的结构基本照着参考例子搭对了，但**按现在这样跑，Fraudster 的 JVM 参数不会被覆盖**。有两个 YAML 写法问题会让配置根本加载不进来，还有一个关键步骤缺了。我先用真实 ansible 把这几个怀疑点逐一验证，不靠猜。The environment was reset; reinstalling ansible.Confirmed, and it's worse than a silent miss: **the playbook doesn't start at all.** Let me see which file it blames and check what `all.yml` does with its own `...`:Workspace 被重置了，之前的文件都没了。我根据上下文重建模板，把「解压之后」的状态模拟出来测：That's my test harness quoting, not your code. Rewriting it with a clean heredoc:## 1. 现在的改动能 work 吗？

**不能。** 我用真实 ansible 把每个怀疑点都复现了：

| # | 问题 | 后果 | 验证结果 |
|---|---|---|---|
| 1 | `DEV_GH.yml` 第 24 行是 `...`，新加的变量写在它**后面** | `YAML parsing failed: Did not find expected <document start>`，**playbook 根本起不来** | 确认。`...` 放在最后一行（比如你 `all.yml` 第 59 行）没问题，后面还有内容才会炸 |
| 2 | `runtime_config_packages: >-` 下面跟一个带引号的 URL | 值是 **str** 不是 list，而且**第一个字符是字面的 `"`**；`setup_config_packages.yml` 里 `[] + str` 报错 | 确认：`can only concatenate list (not "str") to list` |
| 3 | **没有任何步骤把解压出来的 YAML 读回 `environment_jvm_properties`** | 功能不生效。tarball 写的是 `-Xms256m`，渲染出来还是 DEV_GH 的 `-Xms1024m`，ENV_VARS 全丢 | 确认。这是参考例子本来的行为 —— 它解压的是给 app 运行时读的**文件** |
| 4 | `include_tasks` 上的 tags 不会往下传 | `--tags initial` / `--tags config_packages` 下 worker **被静默跳过**，只有全量跑能用 | 确认。只要在外层加 `apply:` 就够 |
| 5 | `notify: "Restart All Application"` | handler 名字对不上会直接报错，**第一次部署一定会触发** | 确认会报错。**你的 handler 名字我没看到，要自己核对** |

1-3 修掉之后我跑通了整条链路：Fraudster 拿到 tarball 的值（`defaults.yml` 的 `-D` 和 `dev-config.yml` 的 `-Xms/-Xmx` 拼接）加两个 ENV_VARS；Mailer 不在 tarball 里，保留 DEV_GH 的值；包没配置就跳过；配置了但文件缺失就硬失败，并且**不会继续渲染启动脚本**。

### 修复 A — `group_vars/DEV_GH.yml`：删掉第 24 行的 `...`，改成 list

```yaml
jdk_version: "{{ lookup('ansible.builtin.env', 'JDK_VERSION', default='java-17-openjdk') }}"

# RUNTIME CONFIG PACKAGES
runtime_config_packages:
  - "https://rp.td.com/repository/application-managed-raw-3rd-party/W000WBR/ansible/app_runtime_config_params/wbr_wbrsvc-fraud-detection/wbr_wbrsvc-fraud-detection_config.tar.gz"

environment_jvm_properties:
  Fraudster: ["-Xms1024m", "-Xmx2048m"]
  Solacer:   ["-Xms512m",  "-Xmx1024m"]
  Cleaner:   ["-Xms512m",  "-Xmx1024m"]
  Mailer:    ["-Xms512m",  "-Xmx1024m"]
```

要保留 `...` 的话只能放在文件**最后一行**。之后改 PAT.yml / PRD.yml 时也注意这两点。

### 修复 B — `group_vars/all.yml`：第 55-58 行换掉

`runtime_config_service` / `runtime_config_nexus_base` / `runtime_config_version` 是之前 LATEST 方案留下来的，现在没有地方用了：

```yaml
# Default EXTERNAL CONFIG PKG
default_config_packages: []

# Per-app runtime values; tasks/apply_runtime_config.yml overrides them
environment_run_args: {}
environment_app_env_vars: {}
...
```

### 修复 C — `deployment.yml`：加 `apply:`，并在启动脚本之前插一步

```yaml
    - name: "Setup External Config Packages (merge common + environment)"
      include_tasks: ./tasks/setup_config_packages.yml
      tags:
        - "always"

    - name: "Deploy External Config Packages from Nexus"
      include_tasks:
        file: ./tasks/deploy_additional_config_packages.yml
        apply:
          tags: ["initial", "deploy_config", "config_packages"]
      tags: ["initial", "deploy_config", "config_packages"]

    - name: "Apply runtime config to JVM args / env vars"
      include_tasks:
        file: ./tasks/apply_runtime_config.yml
        apply:
          tags: ["initial", "deploy_config", "config_packages", "deploy_app_scripts"]
      tags: ["initial", "deploy_config", "config_packages", "deploy_app_scripts"]

    - name: Install App Start Script        # 原来的，不动
      include_tasks: ./tasks/deploy_scripts.yml
```

新这一步也带了 `deploy_app_scripts` tag，这样只重新渲染脚本的时候也会读到 app-config 的值（读的是上次解压到磁盘上的文件，不会重新下载）。

### 修复 D — 新文件 `tasks/apply_runtime_config.yml`

```yaml
---
# ============================================================================
# tasks/apply_runtime_config.yml
#
# 读 extract_archive_nexus.yml 已经解压到磁盘上的 runtime-config YAML，合并进
# environment_jvm_properties / environment_run_args / environment_app_env_vars。
#
# 为什么需要这一步：extract_archive_nexus.yml 只负责把 tarball 解压成文件，这对
# 给 app 运行时读的配置（oauth2、bootstrap.properties）够了；但 JVM 参数要进
# java 命令行，必须在渲染 start_app.sh.j2 之前变成 Ansible 变量。
#
# 顺序：deploy_additional_config_packages.yml 之后，deploy_scripts.yml 之前。
#
# ---- 合并语义 -------------------------------------------------------------
# defaults.yml + <env>-config.yml（跟 00-setup_vars.yml 一致）：
#   list (JVM_ARGS/RUN_ARGS) -> `+` 拼接
#   dict (ENV_VARS)          -> combine(recursive=true)
# 结果 vs group_vars：
#   同名 key 用 app-config 的；只在 group_vars 有的保留；app-config 多的加进去
#   list 按 app 整体替换；dict 按 key 递归合并
#
# runtime_config_packages 为空 = 跳过，group_vars 原封不动。
# ============================================================================

- name: Skip runtime config when no package is configured
  ansible.builtin.debug:
    msg: "runtime_config_packages is empty - keeping group_vars values as-is"
  when: (runtime_config_packages | default([]) | length) == 0

- name: Apply runtime config from extracted package
  when: (runtime_config_packages | default([]) | length) > 0
  # extract_archive_nexus.yml 用 become 解压、owner 是 service_account，
  # 读的时候也 become，免得目录权限收紧后 slurp 读不到。
  become: true
  block:

    - name: Resolve runtime config location
      ansible.builtin.set_fact:
        _rc_dir: "{{ runtime_config_dir | default(app_folders.config) }}"
        _rc_env_prefix: "{{ runtime_config_env_prefix | default(config_environment) }}"

    - name: Check environment config file exists
      ansible.builtin.stat:
        path: "{{ _rc_dir }}/{{ _rc_env_prefix }}-config.yml"
      register: _rc_env_file

    # 配了包但找不到文件就硬失败。静默退回 group_vars 是凌晨三点才会被发现的 bug。
    - name: Fail if environment config is missing
      ansible.builtin.fail:
        msg: >-
          {{ _rc_dir }}/{{ _rc_env_prefix }}-config.yml not found, but
          runtime_config_packages is set. Did deploy_additional_config_packages.yml
          run, and does the tarball contain {{ _rc_env_prefix }}-config.yml?
      when: not _rc_env_file.stat.exists

    - name: Read defaults.yml
      ansible.builtin.slurp:
        src: "{{ _rc_dir }}/defaults.yml"
      register: _rc_defaults_raw

    - name: "Read {{ _rc_env_prefix }}-config.yml"
      ansible.builtin.slurp:
        src: "{{ _rc_dir }}/{{ _rc_env_prefix }}-config.yml"
      register: _rc_env_raw

    - name: Parse both layers
      ansible.builtin.set_fact:
        _rc_def: "{{ _rc_defaults_raw.content | b64decode | from_yaml | default({}, true) }}"
        _rc_env: "{{ _rc_env_raw.content | b64decode | from_yaml | default({}, true) }}"

    # `.get(x) or {}` 两层保护：key 不存在拿到 Undefined，写成 `Solacer:` 后面
    # 什么都没有拿到 None，两种都退回空。
    - name: Merge defaults with environment config
      ansible.builtin.set_fact:
        _rc_merged: >-
          {{ _rc_merged | default({}) | combine({ item: {
               'JVM_ARGS': ((_rc_def.get(item) or {}).get('JVM_ARGS') or [])
                         + ((_rc_env.get(item) or {}).get('JVM_ARGS') or []),
               'RUN_ARGS': ((_rc_def.get(item) or {}).get('RUN_ARGS') or [])
                         + ((_rc_env.get(item) or {}).get('RUN_ARGS') or []),
               'ENV_VARS': ((_rc_def.get(item) or {}).get('ENV_VARS') or {})
                         | combine((_rc_env.get(item) or {}).get('ENV_VARS') or {}, recursive=True)
             }}) }}
      loop: "{{ (_rc_def.keys() | list + _rc_env.keys() | list) | unique | sort }}"
      loop_control:
        label: "{{ item }}"

    - name: Record group_vars values before override
      ansible.builtin.set_fact:
        _rc_before_jvm: "{{ environment_jvm_properties | default({}) }}"

    # length > 0 很关键：上一步给每个 app 都填了三个 key，没配的是空 list/dict，
    # 不判断会拿空列表把 group_vars 里的值冲掉。
    - name: Override environment_jvm_properties from app-config
      ansible.builtin.set_fact:
        environment_jvm_properties: >-
          {{ environment_jvm_properties | default({})
             | combine({item.key: item.value.JVM_ARGS}) }}
      loop: "{{ _rc_merged | default({}) | dict2items }}"
      loop_control:
        label: "{{ item.key }}"
      when: item.value.JVM_ARGS | length > 0

    - name: Override environment_run_args from app-config
      ansible.builtin.set_fact:
        environment_run_args: >-
          {{ environment_run_args | default({})
             | combine({item.key: item.value.RUN_ARGS}) }}
      loop: "{{ _rc_merged | default({}) | dict2items }}"
      loop_control:
        label: "{{ item.key }}"
      when: item.value.RUN_ARGS | length > 0

    - name: Override environment_app_env_vars from app-config
      ansible.builtin.set_fact:
        environment_app_env_vars: >-
          {{ environment_app_env_vars | default({})
             | combine({item.key: item.value.ENV_VARS}, recursive=True) }}
      loop: "{{ _rc_merged | default({}) | dict2items }}"
      loop_control:
        label: "{{ item.key }}"
      when: item.value.ENV_VARS | length > 0

    - name: Runtime config applied
      ansible.builtin.debug:
        msg:
          source: "{{ _rc_dir }}/{defaults,{{ _rc_env_prefix }}-config}.yml"
          jvm_before: "{{ _rc_before_jvm }}"
          jvm_after: "{{ environment_jvm_properties | default({}) }}"
          env_vars_after: "{{ environment_app_env_vars | default({}) }}"
          run_args_after: "{{ environment_run_args | default({}) }}"
```

`setup_config_packages.yml`、`deploy_additional_config_packages.yml`、`extract_archive_nexus.yml` 都**不用改**。

**这两点只能你自己核对：**

- **handler**：打开 `handlers/restart_all_application.yml`，确认里面的 `name:` 一字不差是 `Restart All Application`（参考那边是单数），并且 `deployment.yml` 的 play 里有 `handlers:` 段把它引进来。
- **Nexus 匿名读取**：`extract_archive_nexus.yml` 里的 search 和下载都没带用户名密码。参考 role 在同一个 raw 仓库上能跑，说明大概率允许匿名读；但你之前的 upload 必须用 pwbci。第一次跑如果 search 返回 401，问题就在这里。

## 2. 用 fraud 的 GitHub Action 测 feature branch

**第 0 步 — 推之前本地预检**，1 和 2 这类错误在这里就能抓到：

```bash
cd wbr_actions/ansible/wbr_wbrsvc-fraud-detection
ansible-playbook -i <你的 inventory> deployment.yml --syntax-check
ansible-inventory -i <你的 inventory> --host <DEV_GH 主机名> --yaml | grep -A3 -E 'runtime_config_packages|environment_jvm_properties'
```

第二条要看到 `runtime_config_packages` 下面是 `- https://...`（list，不带引号），而且 `environment_jvm_properties` 有四个 app。

**第 1 步 — 准备一个一眼能认出来的测试值。** 在 wbr-app-config 的 `wbr_wbrsvc-fraud-detection/dev-config.yml` 里改一个无害又显眼的值，比如 `Mailer: {JVM_ARGS: ["-Xms512m", "-Xmx1025m"]}`，再加 `ENV_VARS: {CONFIG_SOURCE: app-config-test}`，然后跑 upload workflow，让 Nexus 上的稳定路径 tarball 带上这个值。1025 这种数字不可能是巧合，验证的时候不会有歧义。

**第 2 步 — 让 fraud 的 deploy workflow 用你的分支。** 在 fraud 仓库开一个 feature branch，找到 checkout `wbr-ghrunner-libs` 的那一步。建议加一个输入参数，而不是直接把 ref 写死：

```yaml
on:
  workflow_dispatch:
    inputs:
      ghrunner_libs_ref:
        description: "wbr-ghrunner-libs branch/tag to deploy with"
        default: "main"

# ...

      - name: Checkout wbr-ghrunner-libs
        uses: actions/checkout@v4
        with:
          repository: TD-Universe/wbr-ghrunner-libs
          ref: ${{ inputs.ghrunner_libs_ref || 'main' }}
          path: wbr-ghrunner-libs
```

这样以后测别的分支也不用再改代码。

**第 3 步 — 只对 DEV_GH 跑一次**，`ghrunner_libs_ref` 填 `04-app-config-externalization`。**必须全量跑或者带 `initial` tag**，第一次需要真正下载解压。

**第 4 步 — 按顺序验证：**

| 看哪里 | 应该看到 |
|---|---|
| log：`Show resolved external config packages` | 一个 list，里面是 tarball 的 URL |
| log：`Download and extract Archive...` | **changed**（第一次运行）；handler 和 Nexus 认证的问题在这一步暴露 |
| log：`Runtime config applied` | `jvm_before` 里 Mailer 是 `-Xmx1024m`，`jvm_after` 里是 `-Xmx1025m` |
| DEV 主机：`ls -la /app/webAS/config/` | `defaults.yml`、`dev-config.yml`、`wbr_wbrsvc-fraud-detection_config.tar.gz.sha256` |
| DEV 主机：`grep -E 'JAVA_OPTS\|CONFIG_SOURCE' /app/webAS/scripts/Mailer/start_*.sh` | `-Xmx1025m` 和 `export CONFIG_SOURCE="app-config-test"` |
| DEV 主机：`ps -ef \| grep wbr-fraud-detection-mailer` | 进程命令行里是 `-Xmx1025m`，说明重启真的生效了 |

**第 5 步 — 再补三个场景：**

- **幂等**：什么都不改再跑一次。应该看到 `Archive package ... is up to date. Skipping download.`，启动脚本不变，**不会**重启。
- **改值生效**：在 wbr-app-config 里把 `-Xmx1025m` 改成 `-Xmx1026m`，upload，再 deploy。应该重新下载、脚本更新、触发重启。
- **回退**：在 DEV_GH.yml 里临时设 `runtime_config_packages: []`。应该看到 `runtime_config_packages is empty`，脚本回到 DEV_GH 的值。

测完记得把 wbr-app-config 里的测试值改回来，再 upload 一次。

还有一个小风险先记下来：tarball 解压到的是**所有 app 共用**的 `/app/webAS/config/` 根目录，`defaults.yml` 这个名字很通用。现在 `default_config_packages: []` 所以没问题；以后如果往里面加了别的包、里面恰好也有一个 `defaults.yml`，两个会互相覆盖。到那时候把 runtime config 单独解压到一个子目录，再设 `runtime_config_dir` 指过去就行，新 task 已经支持这个变量了。
