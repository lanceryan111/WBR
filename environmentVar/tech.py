这两个文件在做的事情:

**Image 1 (`java_wrapper.sh.j2`)** — 一个 shell wrapper 模板,`JVM_OPTS` 和 `RUN_ARGS` 是从 `environment_jvm_properties[application.name]` 这个变量里 join 出来的。

**Image 2 (`spring_boot_app.service.j2`)** — systemd service 模板,`JAVA_OPTS` / `RUN_ARGS` 直接内联写死在 `Environment=` 里,再传给 `ExecStart`。

## 这些 args 一般在哪定义

在 Ansible role 里,变量的定义位置按优先级从低到高,常见的是:

- `roles/<role>/defaults/main.yml` — 放默认值(优先级最低,最适合放可被覆盖的默认 JVM 参数)
- `roles/<role>/vars/main.yml` — 放不太变的固定值
- `group_vars/<group>.yml` 和 `host_vars/<host>.yml` — 按环境/主机区分
- inventory 里的 `environments.yml`(你 tab 上开着的那个)

你现在 `environment_jvm_properties` 这种按 `application.name` 索引的 dict,基本可以确定是定义在 group_vars 或某个 environment 专属的 vars 文件里。可以 grep 一下:

```bash
grep -rn "environment_jvm_properties" --include=*.yml .
grep -rn "java_ms\|java_mx\|app_folders" --include=*.yml .
```

## Externalize 怎么做比较好

核心原则:**模板里只留结构,把值全部抽成变量,再按"层级"分离**。

1. **按作用域分层**
   - 全 app 通用默认 → `defaults/main.yml`
   - 每个 app 特有 → 一个 `dict`,key 是 `application.name`(你已经在做了,保持这个模式)
   - 每个环境(dev/uat/prod)不同的值(堆大小、log path、profile)→ `group_vars/<env>/` 或 `environments.yml`

2. **把两个模板统一成同一个变量来源**
   现在 Image 1 用 `environment_jvm_properties`,Image 2 用内联的 `java_ms`/`java_mx`,两套不一致。建议统一成一个结构,比如:

```yaml
app_jvm_opts:
  wbr-video-details:
    heap_min: "512m"
    heap_max: "2g"
    extra_opts:
      - "-Dcom.td.coreapi.common.config.dir={{ app_folders.oauth }}"
```

3. **敏感值单独走 vault**
   密码、token、密钥不要放明文 vars,用 `ansible-vault` 加密的文件或外部 secret manager,模板里照常 `{{ }}` 引用。

4. **环境差异用同名变量 + 不同 group_vars 文件**,而不是在模板里写 `if env == 'prod'`,保持模板干净。

要不要我看一下你 `environment_jvm_properties` 具体定义在哪个文件、帮你设计一个具体的分层结构?可以贴一下那个 dict 的定义,或者 grep 的结果。

现在结构清楚了,你已经做得比大多数团队规范了。梳理一下现状:

**Image 1 — `group_vars/all.yml`(默认层)**
放的是跨环境不变的东西:`app_folders` 路径、`applications` 列表(每个 app 的 nexus GAV 坐标)、`jdk_version`、`nexus_base_url` 等。

**Image 2 — `group_vars/DEV.yml`(环境层)**
放的是每个环境不同的:`service_account`、`bootstrap_properties`(config server URL、truststore 名字)、密码走 `secrets_env.*`、以及关键的 `environment_jvm_properties`(按 app 名分组,DEV 是 `-Xms1024m` / `-Xmx2048m`)。

这个 `all.yml`(默认) + `<ENV>.yml`(覆盖)的分层就是 Ansible 标准做法,`environment_jvm_properties` 定义在环境层是对的——因为堆大小本来就该按环境变。

## 现在可以改进的几点

**1. 给 `environment_jvm_properties` 在 `all.yml` 补一个默认值**

现在它只在 `DEV.yml` 里存在。如果新加一个环境忘了定义,你 Image 1 里 `java_wrapper.sh.j2` 那句 `environment_jvm_properties[application.name]` 会直接抛 undefined。在 `all.yml` 里放个默认:

```yaml
environment_jvm_properties:
  wbr-thematic-batch:
    - "-Xms512m"
    - "-Xmx1024m"
```

然后 `DEV.yml` / `PROD.yml` 各自覆盖。这样任何环境都有兜底。或者模板里用 `default([])`:

```jinja
{{ environment_jvm_properties[application.name] | default([]) | join(" ") }}
```

**2. 统一两个模板的变量来源**

你上次那两张图里,`java_wrapper.sh.j2` 用的是 `environment_jvm_properties`,而 `spring_boot_app.service.j2` 用的是内联的 `java_ms` / `java_mx`。但我在这两个 env 文件里没看到 `java_ms` / `java_mx` 的定义——它们可能定义在别处,也可能那个 service 模板根本没被这个 app 用。建议 grep 确认一下,别留一个悬空引用:

```bash
grep -rn "java_ms\|java_mx" wbr_wbrsvc-wbr-video-details/
```

理想状态是两个模板都从 `environment_jvm_properties` 取,一个数据源。

**3. `secrets_env.*` 的来源**

你密码已经很干净地抽到 `secrets_env.SPRING_TLS_TRUSTSTORE_PASSWORD` 这类变量了。确认一下这个 `secrets_env` 是从 vault、CI 环境变量,还是外部 secret manager 注进来的——只要不是明文写在某个 vars 文件里就行。这块是唯一真正有安全风险的地方,值得确认。

**4. 命名一致性(小事)**

`jdk_version` 和 `server_default_jdk_version` 都是 `java-17-openjdk`,重复了。如果语义确实不同(一个是 app 用、一个是 server 默认)就保留,否则可以合并减少漂移。

---

总的说你这套 externalize 已经落地得不错,核心就差**给 jvm properties 加默认层**和**统一两个模板的取值来源**这两点。要我帮你写一个 `all.yml` 的默认 `environment_jvm_properties` 加上多环境覆盖的完整例子吗?

可以覆盖,Ansible 的变量优先级里,命令行传入的优先级几乎是最高的。但"用 CADP 运行"这点会影响你具体怎么传,所以分两层说。

## Ansible 本身的覆盖机制

`ansible-playbook` 的 `-e` / `--extra-vars` 优先级最高,压过 group_vars/host_vars/role defaults 所有东西:

```bash
ansible-playbook site.yml -e "environment_jvm_properties={'wbr-thematic-batch': ['-Xms2048m','-Xmx4096m']}"
```

对简单标量值很直接:

```bash
ansible-playbook site.yml -e "jdk_version=java-21-openjdk"
```

但对你这种**嵌套 dict/list**(`environment_jvm_properties`)有个坑:`extra-vars` 里传 dict **不会深度 merge,是整个替换**。也就是说你 `-e` 传了 `wbr-thematic-batch`,如果原本还有别的 app 在这个 dict 里,它们会全丢掉。要么传完整 dict,要么改用更细的变量名单独覆盖。

优先级从低到高大致是:role defaults → group_vars/all → group_vars/ENV → host_vars → play vars → **extra-vars(-e)**。所以你 externalize 到 group_vars 之后,`-e` 永远能压过它。

## CADP 这层才是关键

你是通过 CADP(pipeline)触发的,不是自己在命令行敲 `ansible-playbook`,所以真正的问题是:**CADP 有没有给你暴露传 extra-vars 的入口**。这个我没法凭空判断,取决于你们 pipeline 怎么调 ansible 的。常见几种:

- **Pipeline 参数 → extra-vars**:很多 CADP/CI 配置会把 pipeline 的 input parameters 映射成 `-e key=value` 传给 ansible。如果是这样,你在 pipeline 触发界面填的参数就能覆盖。
- **环境变量注入**:你已经在用 `lookup('env', 'ARTIFACT_VERSION')` 和 `secrets_env.*` 了——说明 CADP 是通过**环境变量**往 ansible 里喂值的。这其实是你现成的、最顺的覆盖通道:在 vars 里写成 `"{{ lookup('env', 'XXX') | default(...) }}"`,然后 CADP 运行时设那个 env var 就能覆盖,不需要动 `-e`。
- **只跑固定 playbook 命令**:如果 pipeline 是硬编码的 `ansible-playbook site.yml` 没有透传参数,那你就没法在运行时覆盖,只能改 group_vars 文件重新提交。

## 建议

你已经在用 `lookup('env', ...)` 这个模式了,对 CADP 来说这是最自然的运行时覆盖方式。如果你想让 jvm opts 也能在 pipeline 运行时临时调,可以写成:

```yaml
environment_jvm_properties:
  wbr-thematic-batch:
    - "-Xms{{ lookup('env', 'JVM_XMS') | default('512m', true) }}"
    - "-Xmx{{ lookup('env', 'JVM_XMX') | default('1024m', true) }}"
```

这样默认走 group_vars 的值,CADP 里设了 `JVM_XMS` / `JVM_XMX` 就覆盖,不用碰 extra-vars,也和你现有的 secrets 注入方式一致。

要确认到底能不能运行时覆盖,得看你们 CADP pipeline 定义里那句调用 ansible 的命令——它长什么样?贴出来我能告诉你走 `-e` 还是走 env var 更靠谱。

