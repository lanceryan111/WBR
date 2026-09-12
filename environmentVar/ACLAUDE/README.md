这次的图把架构说清楚了：deploy 是 Ansible 原生跑的（CADP 上 `ansible_connection: local`），不是我之前设计的 GH Action 那条路。所以 override 必须发生在 play **内部**，作为一个 task —— 之前 `download_app_config.py` / `merge_app_config.py` / `run_ansible_deploy.py` 那三个模块和 `wbr-deploy-app-config.yml` 整条线可以扔掉了，那是给 GH runner → ansible 之间传值用的，现在没有这个边界。

动手之前有一个 schema 问题必须先定，它决定 YAML 长什么样：三个问题的答案：

**Q1 — 怎么 override。** 一个新的 task 文件 `tasks/fetch_runtime_config.yml`，放在 `deployment.yml` 里 "Install App Start Script" **之前**。它做的事：`tempfile` 建临时目录 → 读 `LATEST` 拿版本（或用 `-e runtime_config_version=` 锁定）→ `get_url` 拉 tarball → 解压 → `slurp` 读 `defaults.yml` 和 `<env>-config.yml` → `combine(recursive=True)` 合并 → **`set_fact` 覆盖 `environment_jvm_properties[app]`**。`set_fact` 优先级高于 group_vars，所以后面 `deploy_scripts` 渲染模板时看到的就是 Nexus 的值。清理放在 `block/always` 里，失败也会删。

两个实现细节值得说：用 `slurp` 而不是 `include_vars`，因为 `include_vars` 从**控制节点**读文件，而 tarball 落在**目标机** —— CADP 上 `connection: local` 两者是同一台，但 DEV_GH 走 ssh 就不是了；`slurp` 永远读目标机。另外 play 里**只拉一次**而不是按 app 循环，因为一个 service 一个 tarball，里面按 app 名嵌套，一次 fetch 覆盖整个 `app_list`。

**Q2 — tag 语义，对，就是你想的那样。** tag 叫 `runtime_config`：

- `--tags deploy_app_scripts` → 不拉 Nexus，group_vars 默认值
- `--tags runtime_config,deploy_app_scripts` → 拉最新，覆盖后渲染
- 再加 `-e runtime_config_version=20260904.13` → 锁版本

一个坑：你现有的 `include_tasks` 都是直接写 `tags:`，那**只作用于 include 本身，不传给里面的 task**。`--tags` 过滤时里面没 tag 的 task 会被跳过 —— 包括清理步骤。所以我用了 `apply:` 把 tag 透传进去，这是文档里动态 include 打 tag 的正确写法。我没给它加 `initial`，首次部署要不要拉 Nexus 你自己定。

**Q3 — 之前的文件怎么改。** 变化比较大，因为整条 GH Action deploy 线不需要了：

| 文件 | 处理 |
|---|---|
| `wbr-upload-app-config.yml` | **不动** |
| `package_app_config.py` | 校验改成嵌套 schema（顶层 key 必须是 app 名） |
| `upload_app_config.py` | 每个 tarball 传完后再传一个 `LATEST` 标记文件 |
| `start_app.sh.j2` | 变量解析改成 `environment_jvm_properties[app]` 这种按 app 索引，跟你 PAT.yml 的形状对齐 |
| `wbr-deploy-app-config.yml` | **删** |
| `download/merge/run_ansible_deploy.py` | **删**，逻辑全进了 Ansible task |
| `group_vars_snippet.yml` | **删**，`lookup('env') \| from_json` 那套没有边界要跨了 |

**YAML 要改成嵌套**（你已 commit 的 dev/pat/prod-config.yml 加一层）：

```yaml
ic-batch:
  JVM_ARGS: ["-Xms1024m", "-Xmx2048m"]
  RUN_ARGS: ["D"]
  ENV_VARS: {ENV: pat}
```

**验证**：起了个 http.server 当假 Nexus，用真 `ansible-playbook` 跑了一个跟你 `deployment.yml` 同构的 play：带 tag 时渲染出 `-Xmx4096m`（Nexus 值）、`export ENV="pat"`、defaults 里独有的 `REGION` 保留；不带 tag 渲染出 `-Xmx2048m`（group_vars 值）；tarball 里缺 `prod-config.yml` 时 fatal、临时目录清干净、且 `deploy_scripts` **没有**继续跑；锁版本时 `LATEST` 那步 skipping；拉不存在的版本 404 后也清干净。

两个需要你确认的：

1. **`LATEST` 每次上传都会覆盖**，raw 仓库的 deployment policy 必须允许 redeploy，否则第二次上传就会在这个标记文件上 400。传两次试一下。不行的话就只能锁版本。
2. **`config_environment` 和文件名的对应**：group_vars 叫 `PRD.yml` 但文件叫 `prod-config.yml`。如果 PRD 的 `config_environment` 是 `prd`，要在 PRD.yml 加 `runtime_config_env_prefix: prod`。

`deployment.yml.patch.md` 里有要加到 group_vars 的变量清单和 tag 对照表。Python 两个文件的改动我贴一下：

**`package_app_config.py` — 只有 `_validate_app` 的中段变了：**

```python
        if not isinstance(data, dict):
            print(f"::error file={path}::top level must be a mapping of app names, "
                  f"got {type(data).__name__}")
            ok = False
            continue

        # The single most likely mistake: writing the old flat shape
        # (JVM_ARGS at the top level) instead of nesting under an app name.
        flat_keys = sorted(k for k in data if k in _SHAPE)
        if flat_keys:
            print(f"::error file={path}::{', '.join(flat_keys)} found at the top level. "
                  f"Config must be nested under the app name, e.g. "
                  f"'ic-batch: {{JVM_ARGS: [...]}}'")
            ok = False
            continue

        file_ok = True
        for app_key, app_cfg in data.items():
            if app_cfg is None:
                continue  # `ic-batch:` with nothing under it - allowed, means no override
            if not isinstance(app_cfg, dict):
                print(f"::error file={path}::'{app_key}' must be a mapping, "
                      f"got {type(app_cfg).__name__}")
                file_ok = False
                continue
            for key, want in _SHAPE.items():
                if key in app_cfg and not isinstance(app_cfg[key], want):
                    print(f"::error file={path}::{app_key}.{key} must be a "
                          f"{want.__name__}, got {type(app_cfg[key]).__name__}")
                    file_ok = False
            unknown = sorted(k for k in app_cfg if k not in _SHAPE)
            if unknown:
                print(f"::warning file={path}::{app_key} has keys Ansible will ignore: "
                      f"{', '.join(unknown)}")

        if file_ok:
            log.info("  ok  %s  (apps: %s)", path, ", ".join(sorted(data)) or "none")
        else:
            ok = False
```

**`upload_app_config.py` — 抽了个 `_upload` helper，循环体里传完 tarball 再传 LATEST：**

```python
import tempfile   # 加到 import

def _upload(url, directory, filename, local_path):
    """One raw-repo upload, same payload/files shape as upload_raw_artifact_nexus."""
    payload = {"asset1.filename": filename, "directory": directory}
    with open(local_path, "rb") as fh:
        files = [("asset1", (filename, fh, "application/octet-stream"))]
        gh_nexus_rest_api.upload_nexus_artifact(url, payload, files)
```

```python
        print(f"::group::upload {app}")
        try:
            _upload(url, directory, asset_filename, local_path)
            log.info("uploaded %s/%s", directory, asset_filename)

            # Marker written only after the tarball succeeded, so LATEST never
            # points at a version that is not actually there.
            with tempfile.NamedTemporaryFile("w", suffix="-LATEST", delete=False) as marker:
                marker.write(f"{version}\n")
                marker_path = marker.name
            try:
                _upload(url, directory, "LATEST", marker_path)
                log.info("updated %s/LATEST -> %s", directory, version)
            finally:
                os.unlink(marker_path)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"::error::upload failed for {app}: {exc}")
            failed.append(app)
        finally:
            print("::endgroup::")
```

不需要，两个都删。它们做的事已经原样搬进 `fetch_runtime_config.yml` 了：

| 之前的 Python | 现在的 Ansible task |
|---|---|
| `download_app_config.py` — requests GET + tarfile 解压 | `get_url` + `unarchive` |
| `merge_app_config.py` — 读两个 yml、深度合并、写 JSON 到 `GITHUB_ENV` | `slurp` + `from_yaml` + `combine(recursive=True)` + `set_fact` |

它们当初存在的唯一理由是**跨边界传值**：GH runner 上算好 → 塞进 `GITHUB_ENV` → ansible-playbook 进程用 `lookup('env')` 读。现在 tarball 是在 play **内部**、在目标机上拉的，没有那道边界了，中间不需要 Python 胶水，也不需要 JSON 编码那一套。

`run_ansible_deploy.py` 同理 —— CADP 自己跑 `ansible-playbook`，不需要 Python 帮它拼参数。

留下的 Python 只有上传侧两个：`package_app_config.py` 和 `upload_app_config.py`。我上一轮发文件前已经把那三个从交付目录里删掉了。