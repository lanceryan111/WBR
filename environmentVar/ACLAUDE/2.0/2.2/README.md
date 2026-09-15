这个参考例子很有用，它是你们的**既有家规**，我们的方案有几处应该往上靠。先把它教的东西拆出来：

**1. tarball 用完整 URL 引用，不是我造的那套「service 名 + LATEST 标记 + 拼路径」。**
图1 里 `wbrcore_springboot_application_config_packages` 直接就是一个 Nexus URL 列表，按环境写在 `vars/DEV.yml` 里。这比我的 LATEST 机制简单得多，而且版本锁定天然就在 URL 里。**如果采用，我上一版的 LATEST 标记文件（含 `upload_app_config.py` 里写 LATEST 那段）整个可以删掉。**

**2. 已经有现成的下载器 `extract_archive_nexus.yml`，比我写的好。**
图5 说它会查 Nexus REST 拿 sha256、跟磁盘上已有的 `.sha256` 比对、**只有变了才重新部署**。我那套 `uri` + `get_url` + `unarchive` 没有幂等性，每次都重下。应该直接复用它。

**3. 合并语义：dict 递归 combine，list 用 `+` 拼接。**
图2 第 23-24 行 `ssl_certificates` / `config_packages` 是 `common + env` **拼接**，不是替换。这跟我对 `JVM_ARGS` 做的「按 app 整体替换」不一样。考虑到你说 defaults 和 env 内容不重叠，拼接其实更合适 —— `defaults.yml` 放 `-Dobjectgrid.client.props=...`，`dev-config.yml` 放 `-Xms256m -Xmx512m`，拼起来正好。

**4. `include_vars` 带 `name:` 装进命名空间**（`common_config` / `environment_specific_config`），不污染全局变量。比我的 `slurp` + `from_yaml` 干净。

**5. `set_stats` + `per_host: false`** 把合并结果传给 workflow 里的下一个 playbook。

---

不过有两处**不能照抄**，我得先说明白：

**`extract_archive_nexus.yml` 解压到的是目标机的 `config_dir`,那是给 app 自己读的配置文件。** 我们的场景不一样 —— `JVM_ARGS` 必须进 `java` 命令行，app 运行时读文件是拿不到的，所以它**必须**变成 Ansible 变量。这意味着复用了下载器之后，仍然要有一步把解压出来的 YAML 读进 Ansible。而 `include_vars` 是从**控制节点**读的，文件在目标机上，所以这一步还是得 `slurp`（除非改成在控制节点解压）。

**这两个 role 的架构是两代。** 参考的 `wbnzl-wealthbenzinga` 是 `playbooks/00-setup_vars.yml` + `vars/all.yml` + `vars/DEV.yml`；我们的 `wbr_wbrsvc-fraud-detection` 是 `deployment.yml` + `group_vars/` + `tasks/`。一个用 `vars/` 一个用 `group_vars/`,playbook 也没拆号。

---

等你下一批图，我主要想确认三件事：

1. **`extract_archive_nexus.yml` 的完整内容** —— 它的入参（`wbrcore_springboot_application_archive_package` / `..._deployment_path`）、解压到哪、是不是 `delegate_to` 控制节点。这决定我们是复用它还是只借鉴它的 sha256 幂等思路。
2. **图1 第 22 行 `wbrcore_springboot_application_external_config_url` 后面怎么被消费的** —— 它是新加的（高亮那行），跟 `config_packages` 走的是不是同一条路。如果它就是为「外部配置变成 Ansible 变量」设计的，那我们直接用它，方案能省掉一大半。
3. **fraud-detection 要不要迁到 `wbnzl-wealthbenzinga` 那套结构** —— 还是只借配置合并的思路，保持现在的 `deployment.yml` + `group_vars/`。这个决定改动范围差很多。

在这之前我先不动代码，免得白改。

图1-3 的链路我对照了，**是对的**，补两处细节：

| 环节 | 文件 | 确认 |
|---|---|---|
| Upstream | `vars/DEV.yml` | URL 以 `config_packages` 列表项声明 ✓ |
| Mapper | `00-setup_vars.yml` | `include_vars` 带 `name:` 装进 `common_config`/`environment_specific_config` 命名空间，再合并；**list 用 `+` 拼接，dict 用 `combine(recursive=true)`** ✓ |
| 跨 playbook | `set_stats` + `per_host: false` | 这才是真正把值带到下一个 playbook 的机制，`import_playbook` 只是把 playbook 串起来 |
| Caller | `full_deployment.yml` | `config_packages` → `wbrcore_springboot_config_packages` ✓ |
| Worker | `extract_archive_nexus.yml` | sha256 比对做幂等 ✓ |

**但有一处必须说清楚：这条链路从头到尾没有把 tarball 变成 Ansible 变量。** 它是把 tar.gz 解压成 `/app/webAS/config/<app>` 下的**文件**，给 app 自己运行时读。我们的 `JVM_ARGS` 必须进 `java` 命令行，文件里是读不到的 —— 所以下游那半我们不能照抄，仍然需要"解析成变量"这一步。**能照抄的是上游那半：URL 按环境声明 + mapper 合并。**

图5 第 18-21 行帮了大忙 —— `environment_jvm_properties` **已经存在**，按 app 名（`wbr-thematic-batch`，跟 `applications[].name` 一致）索引，值是 list，而且放在**环境文件**里而不是 `all.yml`。我之前假设的形状是对的。

据此改三件事：

全对：

| 验证点 | 结果 |
|---|---|
| app-config 内部 list **拼接**（家规） | `-Dobjectgrid...`(defaults) + `-Xms256m -Xmx512m`(dev) ✓ |
| vs group_vars **替换** | Fraudster 的 `-Xms1024m/-Xmx2048m` 被换掉 ✓ |
| 只在 group_vars 有的 app | `Mailer` 保留 ✓ |
| 只在 app-config 有的 app | `Cleaner` 加进去 ✓ |
| `Solacer:` 写成空值 | 不崩，空列表被跳过、没污染 ✓ |
| ENV_VARS 递归合并 | `SSL_KEYSTORE` 保留、`SHARED` 被覆盖、两个新 key 加入 ✓ |
| 没配的 RUN_ARGS | `{}`，没被空列表污染 ✓ |

现在把上传侧也改成稳定路径：

**图1-3 的链路确认无误**，但有一处关键差异要说在前面：那条链路从头到尾**没有把 tarball 变成 Ansible 变量** —— 它是解压成 `/app/webAS/config/<app>` 下的文件给 app 运行时读。`JVM_ARGS` 必须进 `java` 命令行，文件里读不到，所以**下游那半照抄不了**。能照抄的是上游：URL 按环境声明 + mapper 合并 + list 拼接 dict 递归。

据此三处改动：

**1. 干掉 LATEST 机制，改用稳定 URL。** 参考里的 URL 是 `dev_oauth2.tar.gz`、`wbr-service-notification_config.tar.gz` —— **不带版本号**，内容变了覆盖上传。这比我造的「版本号文件名 + LATEST 标记」简单得多，也省掉了版本解析那一整段。

**2. app-config 内部 list 改成拼接。** 照 `00-setup_vars.yml` 第 23-24 行。这样 `defaults.yml` 放 `-Dobjectgrid...` 这类通用 `-D`，`<env>-config.yml` 放 `-Xms/-Xmx`,拼起来正好 —— 跟你说的"两边不重叠"天然吻合。

**3. `environment_jvm_properties` 就用图5 的现成形状**，不新造变量。

---

## `tasks/fetch_runtime_config.yml`

```yaml
---
# ============================================================================
# tasks/fetch_runtime_config.yml
#
# 拉 wbr-app-config 发布到 raw Nexus 的 runtime-config tarball，合并进
# environment_jvm_properties / environment_run_args / environment_app_env_vars，
# 供 deploy_scripts 渲染 start_app.sh.j2 时使用。
#
# 入口是一个 URL，按环境写在 group_vars/<ENV>.yml，跟 wbnzl-wealthbenzinga 里
# wbrcore_springboot_application_config_packages / ..._external_config_url
# 一个写法：
#
#   runtime_config_url: "https://rp.td.com/repository/application-managed-raw-3rd-party/\
#     W000WBR/ansible/app_runtime_config_params/wbr_wbrsvc-fraud-detection/\
#     wbr_wbrsvc-fraud-detection_config.tar.gz"
#
# URL 是**稳定路径**（不带版本号），内容变了就重新上传覆盖 —— 跟 dev_oauth2.tar.gz
# / wbr-service-notification_config.tar.gz 一样。所以没有 LATEST 标记文件，也不需要
# 解析版本。要锁版本就把 URL 指向带版本号的那份（upload_app_config 两份都传）。
#
# runtime_config_url 留空 = 整个 task 跳过，group_vars 原封不动。
#
# ---- 优先级（低 -> 高）----------------------------------------------------
#   1. group_vars/all.yml            gh-lib 通用
#   2. group_vars/<ENV>.yml          gh-lib 环境特定（environment_jvm_properties 现在就在这）
#   3. app-config defaults.yml + <env>-config.yml   <- 整体覆盖上面两层
#
# ---- 合并语义 -------------------------------------------------------------
# 第 3 层内部（defaults + <env>-config）—— 照抄 00-setup_vars.yml 的家规：
#   list (JVM_ARGS/RUN_ARGS) -> `+` 拼接。defaults 放 -D 这类通用参数，
#                               <env>-config 放 -Xms/-Xmx，拼起来正好。
#   dict (ENV_VARS)          -> combine(recursive=true)，同名 key 以 env 为准。
#
# 第 3 层 vs group_vars：
#   同名 key -> 用 app-config 的；只在 group_vars 有 -> 保留；app-config 多的 -> 加进去
#   list  -> 按 app 整体替换（app-config 写了某个 app 的列表就整份取代）
#   dict  -> 按 key 递归合并（DEV_GH.yml 里独有的变量不会被冲掉）
#
# ---- tarball 内容 ---------------------------------------------------------
#   defaults.yml, dev-config.yml, pat-config.yml, prod-config.yml, BUILD-INFO.txt
#   顶层 key = app 名，必须跟 all.yml 的 applications[].name 一致：
#     Fraudster:
#       JVM_ARGS: ["-Xms1024m", "-Xmx2048m"]
#       RUN_ARGS: ["--server.port=8443"]
#       ENV_VARS: {SPRING_PROFILES_ACTIVE: pat}
#
# ---- Vars -----------------------------------------------------------------
#   runtime_config_url          group_vars/<ENV>.yml，见上
#   runtime_config_env_prefix   默认取 config_environment。DEV_GH 和 DEV 的
#                               config_environment 都是 dev -> 都读 dev-config.yml
#
# Nexus 凭据从 GH Action / CADP 已 export 的环境变量读，跟 all.yml 读
# ARTIFACT_VERSION 一个写法。临时覆盖：-e nexus_username=... -e nexus_password=...
#
# 用 slurp 而不是 include_vars：include_vars 从控制节点读，tarball 落在目标机。
# CADP 上 connection=local 两者同机，走 ssh 就不是了。
# ============================================================================

- name: Skip runtime config when no URL is configured
  ansible.builtin.debug:
    msg: "runtime_config_url not set - keeping group_vars values as-is"
  when: (runtime_config_url | default('') | trim) | length == 0

- name: Fetch runtime config from Nexus
  when: (runtime_config_url | default('') | trim) | length > 0
  block:

    - name: Resolve runtime-config settings
      ansible.builtin.set_fact:
        _rc_url: "{{ runtime_config_url | trim }}"
        _rc_env_prefix: "{{ runtime_config_env_prefix | default(config_environment) }}"

    - name: Resolve Nexus credentials from environment
      ansible.builtin.set_fact:
        _rc_user: "{{ nexus_username | default(lookup('ansible.builtin.env', 'NEXUS_USERNAME'), true) }}"
        _rc_pass: "{{ nexus_password | default(lookup('ansible.builtin.env', 'NEXUS_PASSWORD'), true) }}"
      no_log: true

    - name: Fail if Nexus credentials are missing
      ansible.builtin.fail:
        msg: "NEXUS_USERNAME / NEXUS_PASSWORD not set and no -e override given"
      when: _rc_user | length == 0 or _rc_pass | length == 0

    - name: Create temp dir for runtime config
      ansible.builtin.tempfile:
        state: directory
        prefix: runtime-config-
      register: _rc_tmp

    - name: "Download {{ _rc_url | basename }}"
      ansible.builtin.get_url:
        url: "{{ _rc_url }}"
        dest: "{{ _rc_tmp.path }}/config.tar.gz"
        url_username: "{{ _rc_user }}"
        url_password: "{{ _rc_pass }}"
        force_basic_auth: true
        mode: "0600"

    - name: Extract runtime config
      ansible.builtin.unarchive:
        src: "{{ _rc_tmp.path }}/config.tar.gz"
        dest: "{{ _rc_tmp.path }}"
        remote_src: true

    - name: Check environment config file exists
      ansible.builtin.stat:
        path: "{{ _rc_tmp.path }}/{{ _rc_env_prefix }}-config.yml"
      register: _rc_env_file

    # 硬失败。文件被改名导致静默只用 defaults 部署，是凌晨三点才会被发现的那种 bug。
    - name: Fail if environment config is missing from the tarball
      ansible.builtin.fail:
        msg: >-
          {{ _rc_env_prefix }}-config.yml not found in {{ _rc_url | basename }}.
          Check runtime_config_env_prefix (defaults to config_environment)
          against the filenames in wbr-app-config.
      when: not _rc_env_file.stat.exists

    - name: Read defaults.yml
      ansible.builtin.slurp:
        src: "{{ _rc_tmp.path }}/defaults.yml"
      register: _rc_defaults_raw

    - name: "Read {{ _rc_env_prefix }}-config.yml"
      ansible.builtin.slurp:
        src: "{{ _rc_tmp.path }}/{{ _rc_env_prefix }}-config.yml"
      register: _rc_env_raw

    - name: Parse both layers
      ansible.builtin.set_fact:
        _rc_def: "{{ _rc_defaults_raw.content | b64decode | from_yaml | default({}, true) }}"
        _rc_env: "{{ _rc_env_raw.content | b64decode | from_yaml | default({}, true) }}"

    # defaults + <env>-config，list 拼接 dict 合并 —— 跟 00-setup_vars.yml 一致。
    # `.get(x) or {}` 两层保护：key 不存在拿到 Undefined，key 存在但值为 null
    # （写成 `Solacer:` 后面什么都没有）拿到 None，两种都退回空。
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
      loop: "{{ ((_rc_def | default({})).keys() | list
                 + (_rc_env | default({})).keys() | list) | unique | sort }}"
      loop_control:
        label: "{{ item }}"

    - name: Record group_vars values before override
      ansible.builtin.set_fact:
        _rc_before_jvm: "{{ environment_jvm_properties | default({}) }}"
        _rc_before_env: "{{ environment_app_env_vars | default({}) }}"

    # ---- app-config 覆盖 group_vars ---------------------------------------
    # length > 0 的判断很关键：上一步给每个 app 都填了三个 key，没配的是空
    # list/dict。不加判断会拿空列表把 group_vars 里好好的值冲掉。
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
          url: "{{ _rc_url }}"
          env_file: "{{ _rc_env_prefix }}-config.yml"
          jvm_before: "{{ _rc_before_jvm }}"
          jvm_after: "{{ environment_jvm_properties | default({}) }}"
          env_vars_before: "{{ _rc_before_env }}"
          env_vars_after: "{{ environment_app_env_vars | default({}) }}"
          run_args_after: "{{ environment_run_args | default({}) }}"

  always:
    # 任何一步失败都会跑到这里，不把带凭据拉下来的文件留在 /tmp。
    - name: Clean up runtime config temp dir
      ansible.builtin.file:
        path: "{{ _rc_tmp.path }}"
        state: absent
      when: _rc_tmp is defined and _rc_tmp.path is defined
```

## `group_vars/DEV_GH.yml` — 接在你图5 第 21 行后面

```yaml
# ---- runtime config tarball（稳定 URL，内容变了覆盖上传）----
runtime_config_url: >-
  https://rp.td.com/repository/application-managed-raw-3rd-party/W000WBR/ansible/app_runtime_config_params/wbr_wbrsvc-fraud-detection/wbr_wbrsvc-fraud-detection_config.tar.gz

# fraud-detection 有四个 app，按图5 的形状把另外三个补全
environment_jvm_properties:
  Fraudster: ["-Xms1024m", "-Xmx2048m"]
  Solacer:   ["-Xms512m",  "-Xmx1024m"]
  Cleaner:   ["-Xms512m",  "-Xmx1024m"]
  Mailer:    ["-Xms512m",  "-Xmx1024m"]
```

`PAT.yml` / `PRD.yml` 同样，URL 不变（同一个 tarball，里面按 `config_environment` 选文件）。`all.yml` 里加 `environment_run_args: {}` 和 `environment_app_env_vars: {}` 两个空声明就够了。

## `upload_app_config.py` — 循环体改成传两份

```python
        print(f"::group::upload {app}")
        try:
            _upload(url, directory, asset_filename, local_path)
            log.info("uploaded %s/%s", directory, asset_filename)

            # Stable copy last, so it only moves forward once the versioned
            # upload actually landed.
            stable_filename = f"{app}_config.tar.gz"
            _upload(url, directory, stable_filename, local_path)
            log.info("uploaded %s/%s  (stable, version %s)",
                     directory, stable_filename, version)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"::error::upload failed for {app}: {exc}")
            failed.append(app)
        finally:
            print("::endgroup::")
```

顶部的 `import tempfile` 可以删掉了。带版本号那份仍然传，用于审计和回滚 —— 要回滚就把 `runtime_config_url` 临时指向带版本号的那个文件。

**一个前置条件要验**：稳定路径每次上传都是覆盖，raw 仓库的 deployment policy 必须允许 redeploy。先对同一个 app 连传两次试一下，第二次要是 400 就说明不允许，那就得回到带版本号的 URL（每次发布改 group_vars）或者找 Nexus 管理员开权限。
