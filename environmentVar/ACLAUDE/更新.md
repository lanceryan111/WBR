# wbr_wbrsvc-fraud-detection — 三处改动

## 1. `group_vars/all.yml` — 在 `nexus_repository` 后面加 3 行

```yaml
nexus_base_url: "https://rp.td.com"                       # 已有
nexus_repository: "application-managed-maven-releases"    # 已有（jar 用的 maven 仓库）

# runtime config tarball（raw 仓库，跟 jar 不是同一个）
runtime_config_service: wbr_wbrsvc-fraud-detection
runtime_config_nexus_base: "{{ nexus_base_url }}/repository/application-managed-raw-3rd-party/W000WBR/ansible/app_runtime_config_params"
runtime_config_version: "{{ lookup('ansible.builtin.env', 'RUNTIME_CONFIG_VERSION', default='') }}"
```

`runtime_config_version` 跟 `ARTIFACT_VERSION` 一个写法：留空走 LATEST，
GH Action / CADP 想锁版本就 `export RUNTIME_CONFIG_VERSION=20260904.13`。

**Nexus 用户名密码不用加。** task 里直接
`lookup('ansible.builtin.env', 'NEXUS_USERNAME')` / `'NEXUS_PASSWORD'`，
GH Action / CADP 已经 export 好的会直接进来。临时跑想换账号：
`-e nexus_username=xxx -e nexus_password=xxx`。

## 2. `deployment.yml` — 第 37 行 "Install App Start Script" 之前插入

```yaml
    - name: Fetch runtime config from Nexus (overrides group_vars)
      include_tasks:
        file: ./tasks/fetch_runtime_config.yml
        apply:
          tags:
            - "runtime_config"
      tags:
        - "runtime_config"

    - name: Install App Start Script          # <- 原第 37 行，不动
      include_tasks: ./tasks/deploy_scripts.yml
```

必须在 deploy_scripts **之前**：override 要先生效，模板才渲染得到。

`apply:` 是必须的，不是风格问题。`include_tasks` 上的 `tags:` 只作用于
include 本身，不透传给里面的 task；`--tags runtime_config` 时里面没 tag 的
task 会被跳过 —— 包括 `always:` 里的临时目录清理。

## 3. `tasks/templates/start_app.sh.j2` — 只动三块

**加**（第 3 行 `set -x` 之后）：4 行 `{% set %}`，从三个 per-app dict 里取值，
取不到就退回原来写死的 `2048m`。

**换**（原第 12-17 行）：

```diff
-# ======== JAVA OPTIONS ========
-export JAVA_HEAP_SIZE_MIN="2048m"
-export JAVA_HEAP_SIZE_MAX="2048m"
-export JAVA_OPTS="-Xms${JAVA_HEAP_SIZE_MIN} -Xmx${JAVA_HEAP_SIZE_MAX} -XX:+CrashOn..."
-
-export RUN_ARGS=""
+# ======== APP ENV VARS ========
+{% for _k, _v in _env_vars | dictsort %}
+export {{ _k }}="{{ _v }}"
+{% endfor %}
+
+# ======== JAVA OPTIONS ========
+export JAVA_OPTS="{{ _jvm_args | join(' ') }} -XX:+CrashOn...（后面那串原样不动）"
+
+export RUN_ARGS="{{ _run_args | join(' ') }}"
```

`JAVA_HEAP_SIZE_MIN/MAX` 两个 export 删了 —— 它们只是用来拼 JAVA_OPTS 的，
现在 `-Xms/-Xmx` 直接从 `JVM_ARGS` 列表来。

**删**（原第 24-30 行 `# >> CONFIGURATION <<` 整块）：在第 22 行 `exit` 之后，
永远跑不到。它想做的事（`environment_jvm_properties[...]` → JVM 参数）现在
就是上面那行 `JAVA_OPTS`。而且它引用的 `application.name` 在这个 role 里
不存在，真跑到也会报错。

`su` 那行、`EXIT_CODE`、`exit` —— 一个字符没动。

## wbr-app-config 里这个 service 的 YAML

顶层 key 必须跟 all.yml 里 `applications[].name` **完全一致**（区分大小写）：

```yaml
# wbr_wbrsvc-fraud-detection/pat-config.yml
Fraudster:
  JVM_ARGS: ["-Xms1024m", "-Xmx4096m"]
  ENV_VARS: {SPRING_PROFILES_ACTIVE: pat}
Solacer:
  JVM_ARGS: ["-Xms512m", "-Xmx1024m"]
Cleaner:
  JVM_ARGS: ["-Xms512m", "-Xmx1024m"]
Mailer:
  JVM_ARGS: ["-Xms512m", "-Xmx1024m"]
```

没写的 app（或没写的 key）保持 group_vars / 模板里的默认值。
