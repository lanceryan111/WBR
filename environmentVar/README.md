# Config tar.gz → Nexus → Ansible template

这套文件按截图中的两个仓库拆分：

- `01-package-config-to-nexus.yml` 放进 **wbr-app-config** 的 `.github/workflows/`。
- `02-download-config-and-deploy.yml` 放进包含 **wbr_actions/ansible** 的部署仓库的 `.github/workflows/`。

默认应用/目录是 `fraud-detection-fraudster`。Nexus 按 raw hosted repository 使用，路径为：

```text
<NEXUS_BASE_URL>/repository/<NEXUS_CONFIG_REPOSITORY>/
  fraud-detection-fraudster/<version>/
    fraud-detection-fraudster-config-<version>.tar.gz
    fraud-detection-fraudster-config-<version>.tar.gz.sha256
```

## GitHub 配置

两个仓库都配置 Repository variables：

```text
NEXUS_BASE_URL=https://nexus.example.com
NEXUS_CONFIG_REPOSITORY=app-config-raw
```

配置仓库把下面两个值设为 Repository secrets；部署仓库把它们设在 `dev`、`pat`、`prod` 对应的 GitHub Environment secrets 中：

```text
NEXUS_USERNAME
NEXUS_PASSWORD
```

部署仓库建立 `dev`、`pat`、`prod` 三个 GitHub Environments；建议为 `prod` 添加 required reviewers。每个 environment 再按认证方式配置：

```text
ANSIBLE_REMOTE_USER
ANSIBLE_PASSWORD
ANSIBLE_BECOME_PASS
ANSIBLE_SSH_PRIVATE_KEY       # 使用私钥时才需要
```

部署仓库可选 Repository variables（不配置时使用右侧默认 group）：

```text
ANSIBLE_LIMIT_DEV=DEV_GH
ANSIBLE_LIMIT_PAT=PAT
ANSIBLE_LIMIT_PROD=PRD
```

如果内部 runner 不是 `[self-hosted, linux]`，请在两份 workflow 中替换 `runs-on`。`actions/checkout@v6` 和 `actions/setup-python@v6` 要求 runner 版本不低于 `2.327.1`；旧企业 runner 可暂时使用 `checkout@v4`、`setup-python@v5`。

## group_vars 必须修改

不能只写下面这种形式：

```yaml
jvm_args: "{{ lookup('env', 'JVM_ARGS') }}"
```

`lookup('env')` 的结果是 JSON 字符串；如果模板直接 `join(' ')`，会按字符拼接。请把截图中 26–27 行附近改成：

```yaml
environment_vars: >-
  {{
    lookup('ansible.builtin.env', 'ENV_VARS')
    | default('{}', true)
    | from_json
  }}

environment_jvm_args: >-
  {{
    lookup('ansible.builtin.env', 'JVM_ARGS')
    | default('[]', true)
    | from_json
  }}

environment_run_args: >-
  {{
    lookup('ansible.builtin.env', 'RUN_ARGS')
    | default('[]', true)
    | from_json
  }}
```

这段需要放到 workflow 所选 inventory group 实际加载的 group_vars 中，例如截图中的 `DEV_GH.yml`、`PAT.yml`、`PRD.yml`。三个文件可放相同解析逻辑；真正的值来自 workflow 下载并合并后的配置。

## `start_app.sh.j2` 必须修改

把下面片段放在实际 Java 启动命令 **之前**，并删除旧的硬编码 heap/JAVA_OPTS/RUN_ARGS。截图中新增块位于 `exit` 后面，那里永远不会执行。

```jinja2
# ===== ENVIRONMENT CONFIGURATION =====
{% for env_name, env_value in environment_vars | dictsort %}
export {{ env_name }}={{ env_value | string | quote }}
{% endfor %}

export JAVA_OPTS={{ environment_jvm_args | join(' ') | quote }}
export RUN_ARGS={{ environment_run_args | join(' ') | quote }}
```

之后原有启动行继续使用同一变量名：

```bash
${JAVA_CMD} ${JAVA_OPTS} -jar "${JARFILE}" ${RUN_ARGS}
```

`deploy_scripts.yml` 不需要改变；它现有的 `ansible.builtin.template` 和 `deploy_app_scripts` tag 会渲染更新后的 `start_app.sh.j2`。

## 合并规则

部署 workflow 会先加载 `defaults.yml`，再递归合并目标文件：

- `ENV_VARS` 这类 map：环境文件只覆盖同名 key，未覆盖的默认 key 保留。
- `JVM_ARGS`、`RUN_ARGS` 这类 list：环境文件中的 list 整体替换默认 list。
- scalar：环境值替换默认值。

`ENV_VARS` 的 key 必须是合法 shell 环境变量名，value 必须写成 YAML string；`JVM_ARGS`、`RUN_ARGS` 必须是 string list。workflow 会在上传和部署前各校验一次。

配置包只应包含非敏感配置。密码、token、private key 等仍应放 GitHub Environment secrets 或 Ansible Vault，不要上传到 Nexus tar.gz。
