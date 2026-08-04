这是一个 **shell 启动脚本**，用来运行一个 Spring Boot 打包好的 Java 应用（jar 包）。逐段拆解：

## 变量定义（15–20 行）
- `JAVA_17_PATH` — 用 find 在系统里搜出 Java 17 的可执行文件路径
- `LOG_PATH` / `APP_CONFIG_PATH` / `APP_JAR_PATH` — 日志目录、配置目录、jar 包位置，都用 `${APPLICATION_NAME}` 拼出来
- `JAVA_HEAP_SIZE_MIN=128m` / `MAX=1024m` — JVM 堆内存下限和上限

## 核心启动命令（28–32 行，就是你高亮那段）
```
${JAVA_17_PATH} -Xms${MIN} -Xmx${MAX} \
  -Dspring.config.additional-location=file:.../bootstrap.properties \
  -DAPI_ENV=sit \
  -jar ${APP_JAR_PATH} 1>> systemout.log 2> systemerror.log
```
翻译一下就是：用 Java 17 启动这个 jar，设定内存范围，加载外部配置文件，把环境标记成 `sit`，然后把标准输出追加到 `systemout.log`、错误输出写到 `systemerror.log`。

## 日志与结果判断（24、26、34–39 行）
- `LOG ... "Staring"` — 启动前记一条日志（"Staring" 是 "Starting" 的拼写错误）
- `if [ $? -eq 0 ]` — 检查上一条命令退出码，`0` 表示成功 → 记 "Finished"，否则记 "FAILURE" 并带上错误码 `$RET`

## 在部署流程里什么时候用到

它属于部署的**最后一步：启动/运行阶段**。典型顺序是：

1. 编译打包 → 生成 `.jar`
2. 把 jar、配置文件推送到目标服务器
3. **执行这个脚本 → 真正把应用跑起来**（就是这里）
4. 脚本记录启动成功/失败，供监控（比如你书签里的 Grafana）追踪

所以每次**发布新版本、重启服务、或调度批处理任务**（文件名带 `thematic-batch`，可能是定时跑的批作业）时，都会调用它。

一个小提醒：`-DAPI_ENV=sit` 把环境**硬编码**成了 SIT（系统集成测试环境）。如果这份脚本要复用到 UAT 或生产，这一行需要改成变量，否则会连错环境。

你现在看的是 `spring_boot_app.service.j2`——一个 **systemd service 单元模板**。这跟第一张图那个 `java_wrapper.sh` 是两条并行的启动方式（一个用 systemd 管理，一个用裸 shell 脚本 + `autosys`）。你高亮的这段就是启动逻辑的核心：

```
Environment="JAVA_OPTS=-Xms{{ java_ms }} -Xmx{{ java_mx }} -DAPI_ENV={{ api_env }} ..."
ExecStart=/bin/sh -c "java ${JAVA_OPTS} -jar {{ app_folders.app_deployment }}/..."
```

现在这些值全是 Jinja 变量，来自 Ansible 的 `all.yml` / `deployment.yml` 那套 group_vars。你想做的是：把这些参数抽到**另一个 repo**，打包传 Nexus，deploy 时下载覆盖默认值。

先说结论：**你的思路方向对，但"打包 jar 传 Nexus 下载覆盖"这一层对于纯配置参数来说偏重了**。我按"能不能不引入新机制"到"确实需要独立 artifact"分几个层次给你建议。

## 核心设计原则:先分清楚三类东西

在动手前先把要"动态化"的参数分类,方案会清晰很多:

1. **运行参数**(java_ms/java_mx/api_env/heap 之类)——变化频率低,适合配置
2. **密钥**(client_secret)——绝对不能进普通配置文件/Nexus,得走 secret store
3. **每环境差异值**(sit/uat/prod 的 url、folder)——本来就该按环境分文件

你想"有改就 override,没改用默认",这在 Ansible 里是**天然支持的**,不需要额外造轮子。

## 方案 A(最推荐):Ansible 变量优先级 + 独立 config repo,不打包 jar

Ansible 的变量优先级本身就是"override or default"机制。做法:

- **默认值**放在 role 的 `defaults/main.yml`(优先级最低,这就是你的"没改就用默认")
- **覆盖值**放在独立 config repo 里,按环境组织成 group_vars/host_vars 结构
- deploy 时把这个 config repo 作为 **extra vars 源**或 checkout 下来,Ansible 自动用高优先级覆盖低优先级

模板不用改结构,只要保证每个变量都有 `default()` 兜底:

```jinja
Environment="JAVA_OPTS=-Xms{{ java_ms | default('128m') }} -Xmx{{ java_mx | default('1024m') }} -DAPI_ENV={{ api_env | default('sit') }}"
```

这样即使 config repo 没提供某个值,模板也不会炸。**这是最省事、最符合 Ansible 惯例的做法,不需要 Nexus。**

## 方案 B:确实想走 Nexus,那就传配置包而不是 jar

如果你们有硬性要求"配置必须版本化、可审计、和 jar 一样从 Nexus 拉"(金融/银行环境常见,你这看起来是 TD),那么:

- config repo 打包成 **tar.gz / zip**(不是 jar,jar 是给 Java 类用的,配置用普通归档更合适),或者做成 **properties/yaml 文件包**
- CI 里传到 Nexus 的 **raw / site repository**(不是 maven repo,配置不是 maven artifact),用版本号或环境名区分
- deploy 时在现有 `Download application artifact` 那个 task 后面加一个 `get_url` 下载 config 包 → 解压 → 用 `include_vars` 载入 → 再渲染模板

这样启动命令读到的就是下载下来的值。关键点:**下载的配置以 `include_vars` 载入到高优先级,role defaults 做兜底**,自动实现 override/default 语义。

## 方案 C:把参数从"模板硬编码"改成"外部 properties 文件"

注意你第一张图的 shell 脚本已经在用 `--spring.config.additional-location=file:.../bootstrap.properties` 了。Spring Boot 本身支持**外部化配置**——与其把 java_ms/java_mx 塞进 systemd 模板,不如:

- 大部分应用行为参数交给 Spring Boot 的 `application-{env}.properties`(这个文件正好可以放在你的 config repo 里,单独版本化)
- systemd 模板里只保留真正的 **JVM 层参数**(-Xms/-Xmx,这些 Spring 管不了,必须在启动命令里)

这样 JVM 参数和应用参数分开管理,各归其位,模板改动最小。

## 几个要提醒你的坑

- **`CLIENT_SECRET` 千万别进 config repo 或 Nexus**。它现在从 `service_secrets.client_secret` 来,应该走 Ansible Vault 或专门的 secret manager,和普通配置分开走。你打包配置时要显式排除它。
- **`Type=simple` + `Restart=always`(21行)**:如果启动参数错了导致进程秒退,systemd 会每 5 秒无限重启(被 `StartLimitBurst=3`/`30s` 拦一下)。参数动态化后,错误配置的影响会被这个重启策略放大,记得在 deploy 后加健康检查。
- **改完要 `systemctl daemon-reload`**:service 模板重新渲染后,不 reload systemd 不会读新的 unit 文件。你的 handler 里得有这步。
- **两套启动方式一致性**:你有 `java_wrapper.sh`(autosys 那条路)和这个 systemd unit 两套。参数动态化要**两边都改**,否则同一个 app 在不同环境行为会不一致。

## 我的建议

如果没有合规硬要求,直接上**方案 A**——用 Ansible 原生的变量优先级 + 独立 config repo,零额外机制,天然 override/default。想再干净点就叠加**方案 C**,让 Spring Boot 管应用参数、systemd 只管 JVM 参数。

只有当"配置必须像 jar 一样过 Nexus、可审计、可回滚到特定版本"是明确要求时,才上**方案 B**,而且用 tar.gz + raw repo,不要用 jar + maven repo。

想让我帮你写出来的话,告诉我:你倾向哪个方案?以及这些参数是**按环境**变(sit/uat/prod 各一套)还是**按应用**变(每个 microservice 一套)?这决定了 config repo 的目录结构怎么设计。

对,就是在 deploy 的 playbook 跑之前(或者第一步),把那个 config repo 的代码拉到 runner 上,然后让 Ansible 去读它。有几种"拉"和"喂给 Ansible"的方式,我从最常见到最灵活排一下。

## 先厘清:两个独立的问题

你这句话其实包含两步,分开看更清楚:

1. **怎么把 config repo 弄到 runner 上** —— checkout / clone
2. **怎么让 Ansible 读这些值并覆盖默认** —— extra vars / include_vars / group_vars

这两步可以自由组合。

## 第一步:把 config repo 弄下来

你们用的是 GitHub(从截图 `wbr-ghrunner-libs`、`TD-Universe` 看是 GitHub Actions self-hosted runner),所以最自然的方式是 **在 GitHub Actions workflow 里多 checkout 一个 repo**,而不是在 Ansible 里 clone:

```yaml
# 在你的 deploy workflow 里
- name: Checkout deploy code
  uses: actions/checkout@v4

- name: Checkout config repo
  uses: actions/checkout@v4
  with:
    repository: TD-Universe/your-config-repo
    ref: ${{ inputs.config_version }}   # 可以指定 branch/tag/sha
    path: config-repo                    # 拉到子目录
    token: ${{ secrets.CONFIG_REPO_PAT }} # 私有 repo 需要
```

这样 config repo 就在 runner 的 `./config-repo/` 下了。**用 GitHub Actions 原生 checkout 比在 Ansible 里 `git` module clone 更好**,因为认证、缓存、ref 管理都由 Actions 处理,不用在 playbook 里塞 token。

(如果确实想在 Ansible 里 clone,是用 `ansible.builtin.git` module,但要自己处理 SSH key / token,更麻烦,不推荐。)

## 第二步:让 Ansible 读这些值(三选一)

假设 config repo 里是这样的结构:

```
config-repo/
  sit/quote-service.yml
  uat/quote-service.yml
  prod/quote-service.yml
```

每个文件内容类似:

```yaml
java_ms: "512m"
java_mx: "2048m"
api_env: "sit"
```

### 选项 1:`-e @file`(最简单,最推荐入门)

在调 ansible-playbook 时,用 `-e @路径` 把文件作为 extra vars 传进去:

```bash
ansible-playbook deploy.yml \
  -e @config-repo/${API_ENV}/quote-service.yml
```

`-e` (extra vars) 是 Ansible **最高优先级**,一定盖过 role 的 `defaults/main.yml`。这完美对应你要的"有就 override,没有就用默认"——config 文件里写了的字段覆盖,没写的字段 fall back 到 defaults。**一行命令,零 playbook 改动,最省事。**

### 选项 2:playbook 里 `include_vars`(更灵活,能加条件)

如果你想在 playbook 内部按环境动态载入:

```yaml
- name: Load environment config
  ansible.builtin.include_vars:
    file: "{{ playbook_dir }}/config-repo/{{ api_env }}/quote-service.yml"
```

`include_vars` 优先级也高于 defaults。好处是可以配合 `when`、`with_first_found`(找不到就用某个 fallback 文件)等逻辑。

### 选项 3:软链成 group_vars(结构化但改动大)

把 config repo 的文件按 inventory group 名组织,链接/复制进 `group_vars/`。这个最"Ansible 正统",但要动 inventory 结构,你现在这套 role 不一定值得。**先别用这个。**

## 兜底:模板一定要有 default()

不管用哪种载入方式,`.service.j2` 里的变量都要加 `default()`,这样 config repo 万一漏了某个字段也不会渲染失败:

```jinja
-Xms{{ java_ms | default('128m') }} -Xmx{{ java_mx | default('1024m') }}
```

这才是真正实现"没改变就用默认值"的地方——**默认值本质上是写在模板的 `default()` 或 role 的 `defaults/main.yml` 里,不是写在 config repo 里**。config repo 只放"要覆盖的东西"。

## 完整链路长这样

```
GitHub Actions workflow:
  1. checkout deploy repo
  2. checkout config repo → ./config-repo/
  3. ansible-playbook deploy.yml -e @config-repo/{env}/quote-service.yml
        ↓
     Ansible 渲染 spring_boot_app.service.j2
        ↓ (extra vars 盖过 defaults,漏掉的字段用 default() 兜底)
     生成最终 systemd unit → daemon-reload → restart
```

## 给你的建议

**先用「GitHub Actions 多 checkout 一个 repo」+「选项 1 的 `-e @file`」组合**,这是改动最小、最符合你需求的路径。跑通了如果嫌命令行拼路径麻烦,再升级到选项 2 的 `include_vars` 加 `with_first_found` 做 fallback。

一个要注意的点:这样做的话 **config repo 的版本和 app 的版本是解耦的**——好处是改配置不用重新 build app,坏处是要在 workflow 里明确记录"这次 deploy 用了 config repo 的哪个 ref",否则出问题不好追溯。建议在 workflow input 里让 config version 可指定(像上面 `ref: ${{ inputs.config_version }}`),并在 deploy 日志里打出来。

要不要我帮你把这套写成一个具体的 workflow 片段 + playbook task,按你现在 `wbr-ms-deploy-app` 这个 role 的结构套进去?你告诉我参数是按环境分还是按每个 service 分就行。

明白。参数**同时按环境和按应用两个维度变化**,所以 config repo 要设计成二维结构,并且要处理"环境层默认 + 应用层覆盖"的叠加。我把完整方案设计出来给你。

先讲清楚一个关键决策:既然两个维度都变,你需要**分层**——否则每个 `env × app` 组合都写全量参数会大量重复(比如 uat 的 heap 设置对所有 app 都一样,不该在每个 app 文件里重复写)。

## Config repo 结构设计

```
wbr-app-config/                      # 你的独立 config repo
├── README.md
├── defaults/
│   └── common.yml                   # 所有 env、所有 app 共享的最低默认(可选)
├── sit/
│   ├── _env.yml                     # sit 环境级默认(所有 app 共享)
│   ├── quote-service.yml            # sit 环境下 quote-service 的覆盖
│   ├── order-service.yml
│   └── ...
├── uat/
│   ├── _env.yml
│   ├── quote-service.yml
│   └── ...
└── prod/
    ├── _env.yml
    ├── quote-service.yml
    └── ...
```

**分层逻辑(优先级从低到高)**:

```
role defaults/main.yml   ← 代码里的兜底,最低
   ↓ 被覆盖
defaults/common.yml      ← 跨环境跨应用的组织级默认
   ↓ 被覆盖
{env}/_env.yml           ← 该环境所有 app 的默认(如 prod 统一大 heap)
   ↓ 被覆盖
{env}/{app}.yml          ← 该环境该应用的精确值,最高
```

这样"没改变就用默认"体现在每一层:app 文件没写的 → 用 env 默认;env 没写的 → 用 common;都没写的 → 用 role defaults 里的 `default()`。

## 文件内容示例

**`sit/_env.yml`**(sit 环境默认,所有 app 共享)
```yaml
api_env: "sit"
java_ms: "256m"
java_mx: "1024m"
nexus_repository: "wbr-snapshots"
```

**`sit/quote-service.yml`**(只写要偏离 env 默认的字段)
```yaml
# quote-service 在 sit 需要更大堆,其他继承 _env.yml
java_mx: "2048m"
```

**`prod/_env.yml`**(prod 统一更大规格)
```yaml
api_env: "prod"
java_ms: "1024m"
java_mx: "4096m"
nexus_repository: "wbr-releases"
```

**`prod/quote-service.yml`**
```yaml
java_mx: "8192m"
extra_java_opts: "-XX:+UseG1GC -XX:MaxGCPauseMillis=200"
```

注意:**app 文件只写"和环境默认不同的东西"**,这是保持可维护性的核心。

## Role defaults(代码 repo 里的兜底)

在 `wbr-ms-deploy-app`(或 quote-service 那个 role)的 `defaults/main.yml`:

```yaml
# 最终兜底,即使 config repo 完全没提供也能启动
java_ms: "128m"
java_mx: "1024m"
api_env: "sit"
extra_java_opts: ""
```

## 模板改造(`spring_boot_app.service.j2`)

关键是**每个变量都要 `default()`**,并把可选的 `extra_java_opts` 拼进去:

```jinja
Environment="JAVA_OPTS=-Xms{{ java_ms | default('128m') }} -Xmx{{ java_mx | default('1024m') }} -DAPI_ENV={{ api_env | default('sit') }} {{ extra_java_opts | default('') }} -Dlog.root.dir={{ app_folders.logs }}/..."
```

这样即便某层没提供 `extra_java_opts`,渲染出来就是空字符串,不会报错。

## GitHub Actions workflow 片段

```yaml
name: Deploy App
on:
  workflow_dispatch:
    inputs:
      environment:
        description: "Target env"
        required: true
        type: choice
        options: [sit, uat, prod]
      application:
        description: "App name (e.g. quote-service)"
        required: true
        type: string
      config_ref:
        description: "Config repo branch/tag/sha"
        required: false
        default: "main"

jobs:
  deploy:
    runs-on: [self-hosted, wbr]
    steps:
      - name: Checkout deploy code
        uses: actions/checkout@v4

      - name: Checkout config repo
        uses: actions/checkout@v4
        with:
          repository: TD-Universe/wbr-app-config
          ref: ${{ inputs.config_ref }}
          path: config-repo
          token: ${{ secrets.CONFIG_REPO_PAT }}

      - name: Run deploy playbook
        run: |
          ansible-playbook deploy.yml \
            -e "target_env=${{ inputs.environment }}" \
            -e "target_app=${{ inputs.application }}" \
            -e @config-repo/defaults/common.yml \
            -e @config-repo/${{ inputs.environment }}/_env.yml \
            -e @config-repo/${{ inputs.environment }}/${{ inputs.application }}.yml
```

**关键点**:`-e @file` 按**从左到右、后者覆盖前者**的顺序生效。所以顺序必须是 common → _env → app,这正好实现你要的分层优先级。而所有 `-e` 又整体高于 role defaults。

## 处理"文件可能不存在"的问题

上面 workflow 有个隐患:如果某个 app 没有专属覆盖文件(完全用 env 默认),`-e @.../quote-service.yml` 会因文件不存在而报错。两种解法:

**解法 1(推荐):workflow 里动态拼参数,只加存在的文件**
```yaml
- name: Build extra vars args
  id: vars
  run: |
    ARGS="-e target_env=${{ inputs.environment }} -e target_app=${{ inputs.application }}"
    for f in \
      config-repo/defaults/common.yml \
      config-repo/${{ inputs.environment }}/_env.yml \
      config-repo/${{ inputs.environment }}/${{ inputs.application }}.yml; do
      [ -f "$f" ] && ARGS="$ARGS -e @$f"
    done
    echo "args=$ARGS" >> "$GITHUB_OUTPUT"

- name: Run deploy playbook
  run: ansible-playbook deploy.yml ${{ steps.vars.outputs.args }}
```

**解法 2:在 playbook 里用 `include_vars` + `with_first_found`/`ignore_errors`**,把"文件不存在就跳过"的逻辑放进 Ansible。如果你更希望逻辑集中在 playbook 而不是 shell,可以走这条。

## 别忘了的两件事

1. **`CLIENT_SECRET` 不进这个 repo**。它继续走 `service_secrets.client_secret`(Ansible Vault / secret manager)。config repo 里绝不出现任何密钥,PR review 时把这条写进规范。
2. **改完 unit 文件要 `daemon-reload` 再 restart**。确认你的 handler 里有 `systemctl daemon-reload` 这一步,否则新参数不生效。

## 落地顺序建议

1. 先建 config repo,把**当前生产实际用的值**照抄进 `_env.yml`(先不做任何优化,保证行为不变)
2. 给 role `defaults/main.yml` 补齐所有变量的兜底值
3. 模板每个变量加 `default()`
4. workflow 加两个 checkout + 拼 `-e` 参数
5. **先在 sit 跑一次,把渲染出的 `.service` 文件和改造前的 diff 一下**,确认逐字节一致或只有预期差异,再推 uat/prod

这样风险最低——第一次上线目标是"行为不变但机制换了",之后再逐步利用新机制调参。

要不要我帮你把 `deploy.yml` 里对应的 `include_vars` 版本(解法 2)也写出来,这样你可以对比 shell 拼参数和 playbook 内处理两种风格,选一个更适合你们团队的?

解法 2 是把"载入配置 + 处理文件缺失"的逻辑放进 playbook/role 内部,workflow 只负责 checkout 和传两个变量(`target_env`、`target_app` 加 config repo 路径)。这样 shell 保持干净,所有 Ansible 逻辑集中在一处。

先说清楚它和解法 1 的分工差异:workflow 不再拼一长串 `-e @file`,只告诉 Ansible **环境、应用、config repo 在哪**,剩下的分层载入全由 `include_vars` 完成。

## Workflow 侧(变简单了)

```yaml
- name: Checkout config repo
  uses: actions/checkout@v4
  with:
    repository: TD-Universe/wbr-app-config
    ref: ${{ inputs.config_ref }}
    path: config-repo
    token: ${{ secrets.CONFIG_REPO_PAT }}

- name: Run deploy playbook
  run: |
    ansible-playbook deploy.yml \
      -e "target_env=${{ inputs.environment }}" \
      -e "target_app=${{ inputs.application }}" \
      -e "config_base={{ '${{ github.workspace }}' }}/config-repo"
```

只传三个变量:目标环境、目标应用、config repo 的绝对路径。

## Playbook / task 侧:分层 include_vars

在你的 role(比如 `wbr-ms-deploy-app/tasks/`)里,**在渲染 `.service.j2` 模板之前**加这段。核心是按优先级从低到高逐层载入,每层用 `first_found` 处理"文件可能不存在":

```yaml
- name: "Load config layer 1 - organization common defaults"
  ansible.builtin.include_vars:
    file: "{{ item }}"
  loop: "{{ q('first_found', params) }}"
  vars:
    params:
      files:
        - "{{ config_base }}/defaults/common.yml"
      skip: true          # 文件不存在就跳过,不报错
  tags:
    - deploy_application
    - upgrade_application
    - initial_application

- name: "Load config layer 2 - environment defaults ({{ target_env }})"
  ansible.builtin.include_vars:
    file: "{{ item }}"
  loop: "{{ q('first_found', params) }}"
  vars:
    params:
      files:
        - "{{ config_base }}/{{ target_env }}/_env.yml"
      skip: true
  tags:
    - deploy_application
    - upgrade_application
    - initial_application

- name: "Load config layer 3 - app override ({{ target_env }}/{{ target_app }})"
  ansible.builtin.include_vars:
    file: "{{ item }}"
  loop: "{{ q('first_found', params) }}"
  vars:
    params:
      files:
        - "{{ config_base }}/{{ target_env }}/{{ target_app }}.yml"
      skip: true
  tags:
    - deploy_application
    - upgrade_application
    - initial_application
```

**几个关键机制解释:**

- **`q('first_found', ...)`** 是 `lookup('first_found', ...)` 的写法。配合 `skip: true`,文件不存在时返回空列表,`loop` 自然什么都不做——这就是"文件缺失自动跳过"的核心,不需要 `ignore_errors`(后者会掩盖真正的错误,不推荐)。
- **顺序即优先级**:三个 task 从上到下执行,后载入的同名变量覆盖先载入的。所以 common → _env → app 的物理顺序,直接决定了覆盖关系。
- **`include_vars` 载入的变量优先级高于 role defaults**,所以最终链路是 `defaults/main.yml < common < _env < app`,完全符合你要的分层。

## 更简洁的写法(合并成一个循环)

上面三段有重复。如果你想紧凑一点,可以用一个 `first_found` 一次性按优先级找,但**注意 `first_found` 默认只返回第一个命中的文件**——那不是我们要的(我们要全部载入并叠加)。所以要用 loop 遍历一个有序列表,逐个 include:

```yaml
- name: "Load layered app config (low → high priority)"
  ansible.builtin.include_vars:
    file: "{{ item }}"
  loop:
    - "{{ config_base }}/defaults/common.yml"
    - "{{ config_base }}/{{ target_env }}/_env.yml"
    - "{{ config_base }}/{{ target_env }}/{{ target_app }}.yml"
  when: item is exists          # 关键:只载入真实存在的文件
  tags:
    - deploy_application
    - upgrade_application
    - initial_application
```

`when: item is exists` 是更直观的"文件存在才载入"判断(`exists` 是 Ansible 的文件测试)。`loop` 保证顺序,顺序保证优先级。**这个版本我更推荐**——比三段 `first_found` 短得多,可读性也好,逻辑一目了然。

## 模板兜底(和之前一致,不变)

`spring_boot_app.service.j2` 里每个变量仍然要有 `default()`,这是最后一道防线——万一三层文件都没提供某字段:

```jinja
Environment="JAVA_OPTS=-Xms{{ java_ms | default('128m') }} -Xmx{{ java_mx | default('1024m') }} -DAPI_ENV={{ api_env | default('sit') }} {{ extra_java_opts | default('') }}"
```

## 两个容易踩的坑

1. **`config_base` 必须是绝对路径**。`include_vars` 的 `file:` 相对路径是相对 role 的 `vars/` 目录解析的,不是相对 playbook,很容易找错。所以 workflow 里用 `github.workspace` 拼绝对路径传进来最稳。

2. **载入配置的 task 必须排在渲染模板的 task 之前**。Ansible 是顺序执行的,变量得先载入内存,后面 `template:` 生成 `.service` 文件时才读得到新值。放到 `tasks/main.yml` 的开头区域最安全。

## 解法 1 vs 解法 2 怎么选

- **解法 1(workflow 拼 `-e`)**:逻辑在 shell,Ansible role 零改动,适合你不想动现有 role、或配置逻辑简单的情况。缺点是 shell 脚本变复杂,`-e` 优先级最高有时会盖掉你本不想盖的东西。
- **解法 2(playbook `include_vars`)**:逻辑在 Ansible,workflow 干净,分层关系在 role 里看得一清二楚,团队其他人读 role 就懂配置怎么来的。缺点是 role 要改。**如果这套 deploy 机制会长期维护、多人协作,选解法 2。**

建议直接用解法 2 里那个 **`loop` + `when: item is exists`** 的简洁版,配合模板的 `default()`,这是可读性和健壮性最平衡的组合。

要不要我帮你把这几个 task 按 `wbr-ms-deploy-app` 现有 `tasks/main.yml` 的结构(它现在应该 include 了 `multi_app.yml`)拼成一个可以直接放进去的完整片段,包括放在哪个 include 之前?

好。方案 B 是"配置打包传 Nexus、deploy 时下载解压再载入"。相比方案 A 从 GitHub checkout,B 的差别只在**前半段"怎么把配置弄到 runner 上"**——从"git checkout"换成"从 Nexus 下载 + 解压"。后半段"怎么让 Ansible 读并覆盖"的解法 1 / 解法 2 逻辑基本复用方案 A,只是路径指向解压目录。

先讲清楚 B 特有的几个决策,再给两个解法。

## B 方案特有的设计决策

**1. 打包格式:tar.gz,不是 jar**
配置是普通文件,用 tar.gz。jar 是给 Java 类加载器的,拿来装配置会让人误解,也用不上 jar 的任何特性。

**2. Nexus repo 类型:raw (hosted),不是 maven**
配置不是 maven artifact,没有 groupId/artifactId/version 的 POM 语义。用 Nexus 的 **raw repository**(或 site repo),按路径直接存取,最简单。

**3. 打包粒度:整个 config repo 打成一个包,按版本号区分**
不要按 env 或 app 拆成很多小包(那样版本管理是噩梦)。整个 config repo 打一个 `wbr-app-config-<version>.tar.gz`,内部仍是方案 A 那个 `{env}/{app}.yml` 二维结构。deploy 时下载整包、解压,再按 env/app 挑对应文件。

## Config 包内部结构(和方案 A 相同)

```
wbr-app-config-1.4.2.tar.gz  解压后:
config/
├── defaults/common.yml
├── sit/
│   ├── _env.yml
│   ├── quote-service.yml
│   └── ...
├── uat/
│   ├── _env.yml
│   └── ...
└── prod/
    ├── _env.yml
    ├── quote-service.yml
    └── ...
```

分层优先级依旧:`role defaults < common < {env}/_env < {env}/{app}`。

## 打包 + 上传(在 config repo 的 CI 里做,一次性)

config repo 自己的 CI(合并到 main 或打 tag 时触发)负责打包上传:

```yaml
# config repo 的 .github/workflows/publish.yml
name: Publish config to Nexus
on:
  push:
    tags: ["v*"]
jobs:
  publish:
    runs-on: [self-hosted, wbr]
    steps:
      - uses: actions/checkout@v4

      - name: Package config
        run: |
          VERSION="${GITHUB_REF_NAME#v}"     # v1.4.2 → 1.4.2
          tar czf "wbr-app-config-${VERSION}.tar.gz" config/
          echo "VERSION=${VERSION}" >> "$GITHUB_ENV"

      - name: Upload to Nexus raw repo
        run: |
          curl -sf -u "${{ secrets.NEXUS_USER }}:${{ secrets.NEXUS_PASS }}" \
            --upload-file "wbr-app-config-${VERSION}.tar.gz" \
            "${{ vars.NEXUS_BASE_URL }}/repository/wbr-raw/app-config/wbr-app-config-${VERSION}.tar.gz"
```

上传后,Nexus 上就有一个按版本号可寻址的配置包:
`.../repository/wbr-raw/app-config/wbr-app-config-1.4.2.tar.gz`

**关键**:config 包的版本和 app jar 的版本**解耦**,各自独立发布、独立回滚。deploy 时两个版本号都要显式指定并记录。

---

# 解法 1:下载解压在 workflow 做,Ansible 用 `-e @file`

逻辑集中在 deploy workflow 的 shell,Ansible role 零改动。

## Deploy workflow

```yaml
on:
  workflow_dispatch:
    inputs:
      environment: { type: choice, options: [sit, uat, prod], required: true }
      application: { type: string, required: true }   # e.g. quote-service
      config_version: { type: string, required: true } # e.g. 1.4.2

jobs:
  deploy:
    runs-on: [self-hosted, wbr]
    steps:
      - name: Checkout deploy code
        uses: actions/checkout@v4

      - name: Download & extract config from Nexus
        run: |
          mkdir -p config-repo
          curl -sf -u "${{ secrets.NEXUS_USER }}:${{ secrets.NEXUS_PASS }}" \
            "${{ vars.NEXUS_BASE_URL }}/repository/wbr-raw/app-config/wbr-app-config-${{ inputs.config_version }}.tar.gz" \
            -o config.tar.gz
          tar xzf config.tar.gz -C config-repo   # 解压出 config-repo/config/...

      - name: Build extra-vars args (only existing files)
        id: vars
        run: |
          BASE="config-repo/config"
          ENV="${{ inputs.environment }}"
          APP="${{ inputs.application }}"
          ARGS="-e target_env=$ENV -e target_app=$APP"
          for f in \
            "$BASE/defaults/common.yml" \
            "$BASE/$ENV/_env.yml" \
            "$BASE/$ENV/$APP.yml"; do
            [ -f "$f" ] && ARGS="$ARGS -e @$f"
          done
          echo "args=$ARGS" >> "$GITHUB_OUTPUT"

      - name: Run deploy playbook
        run: ansible-playbook deploy.yml ${{ steps.vars.outputs.args }}
```

**要点:**
- `for` 循环 `[ -f "$f" ]` 判断存在才加 `-e @`,处理"某 app 没专属文件"的情况(和方案 A 解法 1 同款)。
- `-e @file` 从左到右后者覆盖前者,顺序 common → _env → app 即优先级。整体 `-e` 高于 role defaults。
- 下载用 `curl -sf`:`-f` 让 HTTP 错误(如版本不存在返回 404)直接使 step 失败,不会静默继续。

## 模板兜底(不变)

`spring_boot_app.service.j2` 每个变量加 `default()`,略(同前面)。

---

# 解法 2:下载在 workflow,解压+载入在 Ansible

workflow 只下载 tar.gz 并把路径传进去,**解压和分层载入都在 role 里做**。逻辑集中在 Ansible,workflow 最干净。

## Deploy workflow(更薄)

```yaml
      - name: Download config tarball from Nexus
        run: |
          curl -sf -u "${{ secrets.NEXUS_USER }}:${{ secrets.NEXUS_PASS }}" \
            "${{ vars.NEXUS_BASE_URL }}/repository/wbr-raw/app-config/wbr-app-config-${{ inputs.config_version }}.tar.gz" \
            -o "${{ github.workspace }}/config.tar.gz"

      - name: Run deploy playbook
        run: |
          ansible-playbook deploy.yml \
            -e "target_env=${{ inputs.environment }}" \
            -e "target_app=${{ inputs.application }}" \
            -e "config_tarball=${{ github.workspace }}/config.tar.gz"
```

甚至下载也可以搬进 Ansible(用 `get_url`),让 workflow 只传 Nexus URL——但把认证 secret 传进 playbook 更麻烦,**下载留在 workflow、解压载入留在 Ansible** 是更干净的分工。

## Role 侧 tasks(解压 + 分层载入)

在渲染 `.service.j2` **之前**加这几个 task:

```yaml
- name: "Prepare config extract dir"
  ansible.builtin.file:
    path: "/tmp/wbr-app-config"
    state: directory
    mode: "0700"
  tags: &cfg_tags
    - deploy_application
    - upgrade_application
    - initial_application

- name: "Extract config tarball"
  ansible.builtin.unarchive:
    src: "{{ config_tarball }}"
    dest: "/tmp/wbr-app-config"
    remote_src: false          # tar.gz 在 runner(controller)本地,不在目标机
  tags: *cfg_tags

- name: "Load layered app config (low → high priority)"
  ansible.builtin.include_vars:
    file: "{{ item }}"
  loop:
    - "/tmp/wbr-app-config/config/defaults/common.yml"
    - "/tmp/wbr-app-config/config/{{ target_env }}/_env.yml"
    - "/tmp/wbr-app-config/config/{{ target_env }}/{{ target_app }}.yml"
  when: item is exists
  tags: *cfg_tags
```

**要点:**
- `unarchive` 直接解压 tar.gz,`remote_src: false` 表示压缩包在运行 Ansible 的机器(你的 self-hosted runner)本地。如果你的 deploy 是推到远端目标机执行,这里要按实际拓扑调整(见下面的坑)。
- `loop` + `when: item is exists`:顺序即优先级,文件不存在自动跳过——和方案 A 解法 2 完全一致的健壮写法。
- `include_vars` 优先级高于 role defaults,叠加关系成立。
- `tags: &cfg_tags` / `*cfg_tags` 是 YAML 锚点,避免每个 task 重复抄三个 tag。

## 模板兜底(不变)

同前,每个变量 `default()`。

---

## B 方案要特别注意的坑

**1. `remote_src` 和执行拓扑**
你现有 role 里 `get_url` 是下载到目标机的(`dest: "{{ deploy_app_folder }}/..."`)。如果 deploy 实际是在**目标机上**跑 task,那 config tar.gz 也得先弄到目标机,`unarchive` 的 `remote_src` 要设 `true`,或者干脆在 role 里也用 `get_url` 从 Nexus 下到目标机再解压。**先确认你的 playbook 是 local 执行还是 push 到 remote host,这决定 tarball 放哪、`remote_src` 怎么设。**

**2. Nexus 认证不要进 playbook**
解法 2 若用 `get_url` 从 Nexus 下,`url_username`/`url_password` 会出现在 task 里。宁可保持"下载在 workflow(用 GitHub secret),解压载入在 Ansible",避免 Nexus 凭据进 Ansible 变量层。

**3. 清理临时文件**
`/tmp/wbr-app-config` 解压出来的配置用完该清掉(尤其如果里面有敏感值),末尾加个 `file: state=absent`。

**4. `CLIENT_SECRET` 依旧不进这个包**
config 包里绝不含密钥,继续走 Vault / secret manager。打包 CI 里最好加一步 grep 扫描,发现疑似 secret 就 fail。

**5. 版本可追溯**
config 包版本和 app 版本解耦是 B 的核心价值(可独立回滚),但代价是 deploy 时必须记录"这次用了 config `1.4.2` + app `x.y.z`"。在 deploy 日志和 `ansible.builtin.debug` 里把两个版本都打出来。

---

## A vs B、解法 1 vs 2 怎么选

- **A(GitHub checkout)** 更轻,适合配置迭代快、不需要强审计的场景。
- **B(Nexus 打包)** 重一些,但配置像 jar 一样版本化、可审计、可回滚到精确版本——银行/合规环境(你这看着是 TD)常有这类要求时选 B。
- **解法 1**:逻辑在 workflow,role 零改动,配置逻辑简单时够用。
- **解法 2**:逻辑在 Ansible role,workflow 干净,分层关系集中可读,长期多人维护选它。

**如果 B 是硬要求,我建议 B + 解法 2**:配置的"下载来源"由 workflow 管,"如何解析叠加"由 role 管,职责清晰,role 里一眼看清配置怎么来的。

要落地的话,我需要先确认一件事:你的 deploy playbook 是在 **runner 本地执行(localhost)** 还是 **通过 SSH 推到远端目标机执行**?这直接决定解法 2 里 tarball 放哪、`remote_src` 和解压路径怎么设。告诉我拓扑,我帮你把 task 按 `wbr-ms-deploy-app` 的实际结构调准。

好,SSH 推到远端目标机执行,这改变了解法 2 里几个关键点:tarball 和解压目录都要在**目标机**上,`include_vars` 载入的文件也必须在目标机能读到。我把解法 2 按远端拓扑重新调准,并顺带说解法 1 在这个拓扑下的差异。

先讲清楚这个拓扑下的核心矛盾:

- **`include_vars` 是在 controller(runner)上执行的** —— 它读的是 controller 本地的文件,把变量载入内存,然后才渲染模板、推到远端。
- **`unarchive` / `get_url` 的 `remote_src` 和 `delegate_to`** —— 决定文件操作发生在 controller 还是 target。

所以有个反直觉的点:**配置文件最终要让 `include_vars` 读到,而 `include_vars` 跑在 controller 上**。这意味着解压这一步,放在 controller 上其实更顺——配置是"渲染模板的输入",本就该在 controller 侧处理,不需要下发到目标机。

## 推荐做法:配置在 controller 处理,只有渲染结果推到远端

想清楚数据流:

```
Nexus ──下载 tar.gz──> controller(runner)
                          │ 解压
                          │ include_vars 载入变量(在 controller 内存)
                          │ 渲染 .service.j2
                          └──template 推送渲染结果──> target host
```

配置包**根本不需要上目标机**。它只是渲染模板的原料,渲染在 controller 完成,最终只有生成好的 `.service` 文件通过 `template` 模块推到远端。这样最干净,也避免把配置(可能含敏感值)散落到目标机。

## 解法 2(SSH 远端版)

### Workflow(不变,下载到 runner 本地)

```yaml
      - name: Download config tarball from Nexus
        run: |
          curl -sf -u "${{ secrets.NEXUS_USER }}:${{ secrets.NEXUS_PASS }}" \
            "${{ vars.NEXUS_BASE_URL }}/repository/wbr-raw/app-config/wbr-app-config-${{ inputs.config_version }}.tar.gz" \
            -o "${{ github.workspace }}/config.tar.gz"

      - name: Run deploy playbook
        run: |
          ansible-playbook -i inventory deploy.yml \
            -e "target_env=${{ inputs.environment }}" \
            -e "target_app=${{ inputs.application }}" \
            -e "config_tarball=${{ github.workspace }}/config.tar.gz"
```

### Role tasks:解压 + 载入都 `delegate_to: localhost`

关键是这几个 task **强制在 controller 上执行**,用 `delegate_to: localhost` + `run_once: true`:

```yaml
- name: "Prepare config extract dir on controller"
  ansible.builtin.file:
    path: "{{ config_extract_dir }}"
    state: directory
    mode: "0700"
  delegate_to: localhost
  run_once: true
  tags: &cfg_tags
    - deploy_application
    - upgrade_application
    - initial_application

- name: "Extract config tarball on controller"
  ansible.builtin.unarchive:
    src: "{{ config_tarball }}"
    dest: "{{ config_extract_dir }}"
    remote_src: false        # 源在 controller 本地
  delegate_to: localhost
  run_once: true
  tags: *cfg_tags

- name: "Load layered app config (low → high priority)"
  ansible.builtin.include_vars:
    file: "{{ item }}"
  loop:
    - "{{ config_extract_dir }}/config/defaults/common.yml"
    - "{{ config_extract_dir }}/config/{{ target_env }}/_env.yml"
    - "{{ config_extract_dir }}/config/{{ target_env }}/{{ target_app }}.yml"
  when: item is exists
  # include_vars 本就在 controller 执行,读的是 controller 上解压出的文件
  tags: *cfg_tags
```

配一个变量(比如 role `defaults/main.yml` 或 playbook vars):

```yaml
config_extract_dir: "/tmp/wbr-app-config-{{ target_env }}-{{ target_app }}"
```

**为什么这样对:**
- `delegate_to: localhost` + `run_once: true`:即使 inventory 里有多台目标机,解压只在 controller 做一次,不会每台机重复解压(配置对所有目标机是同一份)。
- `include_vars` 天然在 controller 跑,`when: item is exists` 测的也是 controller 上的文件——和解压目录对得上。
- 载入的变量对**所有** play hosts 生效,后续渲染 `.service.j2` 时每台目标机都能用。

### 渲染模板(推到远端,这步才碰目标机)

```yaml
- name: "Render systemd service unit to target"
  ansible.builtin.template:
    src: "spring_boot_app.service.j2"
    dest: "/etc/systemd/system/{{ target_app }}.service"
    owner: root
    group: root
    mode: "0644"
  become: true
  notify: "Reload systemd and restart service"
  tags: *cfg_tags
```

这里没有 `delegate_to`,所以在**目标机**执行——变量已经在 controller 内存里备好,`template` 渲染时直接用,把结果写到目标机的 `/etc/systemd/system/`。

### 清理(controller 上)

```yaml
- name: "Cleanup extracted config on controller"
  ansible.builtin.file:
    path: "{{ config_extract_dir }}"
    state: absent
  delegate_to: localhost
  run_once: true
  tags: *cfg_tags
```

### Handler(目标机上 reload + restart)

```yaml
# handlers/main.yml
- name: "Reload systemd and restart service"
  ansible.builtin.systemd:
    name: "{{ target_app }}"
    state: restarted
    daemon_reload: true      # 等价于 daemon-reload,unit 改了必须做
    enabled: true
  become: true
```

`systemd` 模块的 `daemon_reload: true` 一步搞定"改了 unit 文件要重载"——比自己敲 `systemctl daemon-reload` 干净。

## 解法 1(SSH 远端版)的差异

解法 1 是 workflow 里拼 `-e @file`,而 `-e @file` 读的也是 **controller 本地文件**。所以解法 1 在远端拓扑下几乎不用改——下载解压在 workflow(runner 本地)做,`-e @` 指向 runner 本地解压路径,Ansible 载入后渲染再推远端。也就是说:

```yaml
      - name: Download & extract config
        run: |
          mkdir -p config-repo
          curl -sf -u "..." ".../wbr-app-config-${{ inputs.config_version }}.tar.gz" -o config.tar.gz
          tar xzf config.tar.gz -C config-repo

      - name: Build extra-vars args
        id: vars
        run: |
          BASE="config-repo/config"; ENV="${{ inputs.environment }}"; APP="${{ inputs.application }}"
          ARGS="-e target_env=$ENV -e target_app=$APP"
          for f in "$BASE/defaults/common.yml" "$BASE/$ENV/_env.yml" "$BASE/$ENV/$APP.yml"; do
            [ -f "$f" ] && ARGS="$ARGS -e @$f"
          done
          echo "args=$ARGS" >> "$GITHUB_OUTPUT"

      - name: Run deploy playbook
        run: ansible-playbook -i inventory deploy.yml ${{ steps.vars.outputs.args }}
```

Role 里只需要渲染模板 + handler 那部分(跟解法 2 后半段相同),**不需要 unarchive/include_vars 的 task**——配置已经通过 `-e` 进内存了。

**所以远端拓扑下的一个重要结论**:配置文件全程留在 controller,不下发目标机。无论解法 1 还是 2,目标机只接收"渲染好的 `.service` 文件"。这既简单又安全。

## 什么时候配置才真的要上目标机

只有一种情况例外:如果你的 `.service.j2` 里用 `EnvironmentFile=` 指向目标机上的一个 properties 文件(而不是把值 inline 进 `Environment=`),那才需要把某个渲染后的 env 文件推到目标机。但你现在截图里是 `Environment="..."` 直接内联的,不涉及这个,配置留 controller 即可。

## 落地检查清单

1. 确认 runner 到目标机的 SSH 免密/密钥已配好,inventory 里目标机分组正确(按 env 分组最好,`sit`/`uat`/`prod` 各一组)。
2. `become: true` 写 `/etc/systemd/system/` 需要 sudo 权限,确认 service account 在目标机有对应 sudoers。
3. `config_extract_dir` 带上 env+app 后缀,避免同一 runner 并发部署不同 app 时互相覆盖解压目录。
4. 先在 sit 单台跑,把渲染出的 `.service` 和改造前 diff,确认一致再扩到多机和 uat/prod。
5. `CLIENT_SECRET` 仍走 Vault,不进 config 包。

要不要我把解法 2 这一整套(解压→载入→渲染→handler→清理)按你 `wbr-ms-deploy-app` role 里 `tasks/main.yml` 现有的 include 顺序,拼成一个可以直接贴进去的完整文件,并标好插在哪个现有 task 之前?这样你拿过去就能对着改。
