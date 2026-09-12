# deployment.yml — 需要加的部分

只加一个 task，放在 **"Install App Start Script" 之前**（图2 第 37 行之前）。
顺序很重要：override 必须先于 deploy_scripts 渲染 start_app.sh.j2。

```yaml
    # ---- 加在 "Install Certificates" 之后、"Install App Start Script" 之前 ----
    - name: Fetch runtime config from Nexus (overrides group_vars)
      include_tasks:
        file: ./tasks/fetch_runtime_config.yml
        apply:
          tags:
            - "runtime_config"
      tags:
        - "runtime_config"

    - name: Install App Start Script          # <- 你已有的，不动
      include_tasks: ./tasks/deploy_scripts.yml
      ...
```

## 为什么用 `apply:`

你现有的 include 都是直接写 `tags:`，那对 `include_tasks` 只作用于 include
本身，**不会传给被 include 文件里的 task**。`--tags` 过滤时，里面没打 tag
的 task 会被跳过 —— 包括 `always:` 里的清理步骤。`apply:` 把 tag 透传进去，
这是 Ansible 文档里给动态 include 打 tag 的正确写法。

## tag 语义（回答你的问题 2）

| 命令 | 结果 |
|---|---|
| `--tags deploy_app_scripts` | 不拉 Nexus，用 group_vars 里的默认值渲染 |
| `--tags runtime_config,deploy_app_scripts` | 拉 Nexus 最新，override 后渲染 |
| `--tags runtime_config,deploy_app_scripts -e runtime_config_version=20260904.13` | 锁定版本 |
| 不带 `--tags`（全量） | 会拉。要不要拉由你决定 —— 不想的话就不给它加 `initial` |

我**没有**给它加 `initial` tag。首次部署要不要从 Nexus 拉，看你们流程：
- 加了：`--tags initial` 也会拉，首次部署就用 Nexus 的值
- 不加：首次部署用 group_vars 默认值，之后想切到 Nexus 再显式带 `runtime_config`

## 需要加到 group_vars 的变量

放 `group_vars/all.yml`（每个 role 一份，因为 service 名不同）：

```yaml
# 这个 role 对应 wbr-app-config 里哪个文件夹
runtime_config_service: wbr_wbrsvc-wbr-thematic-ingestion

# 跟 upload workflow 的 NEXUS_DIRECTORY_PATH 对上
runtime_config_nexus_base: https://rp.td.com/repository/application-managed-raw-3rd-party/W000WBR/ansible/app_runtime_config_params

# 留空 = 用 LATEST；prod 建议在 -e 里锁定
runtime_config_version: ""

# 拉 jar 的 Nexus 凭据用什么，这里就用什么
nexus_username: "{{ ... }}"
nexus_password: "{{ ... }}"
```

`runtime_config_env_prefix` 默认取 `config_environment`。注意 group_vars 叫
`PRD.yml` 但文件叫 `prod-config.yml` —— 如果 PRD 的 `config_environment` 是
`prd`，要么在 PRD.yml 里加 `runtime_config_env_prefix: prod`，要么把文件改名。
