图1 那个模板我确实理解偏了，图2 的问题也直接相关 —— 两个都归到同一件事：**优先级链到底是几层、谁压谁**。我先把当前 `fetch_runtime_config.yml` 的实际行为跑出来，再确认你要的顺序。

`uri` 模块在这个沙箱里缺依赖。优先级问题不需要网络 —— 我直接测 merge + set_fact 那段逻辑。

测出来了，当前实现确实有问题。四层的实际结果：

| 层 | 来源 | 值 | 结果 |
|---|---|---|---|
| 1 | `group_vars/all.yml` | `Xmx=1111` | 被 DEV_GH.yml 盖掉（Ansible 原生行为） |
| 2 | `group_vars/DEV_GH.yml` | `Xmx=2222` | **被 app-config 的 defaults.yml 盖掉** ← 问题 |
| 3 | app-config `defaults.yml` | `Xmx=3333` | **最终生效** |
| 4 | app-config `dev-config.yml` | 没写 JVM_ARGS | — |

两个真问题：

**一、`defaults.yml` 会盖掉 `DEV_GH.yml`。** 就算 `dev-config.yml` 压根没写 `JVM_ARGS`，只要 `defaults.yml` 写了，环境特定的 `DEV_GH.yml` 就被通用值顶掉了。按你的说法 defaults 是"app 正常运行默认的"，这明显反了。

**二、`ENV_VARS` 是整体替换，不是按 key 合并。** `DEV_GH.yml` 里的 `FROM_DEV_GH` 在最终结果里**直接消失**了 —— 只剩 app-config 那边的 key。

改之前要把顺序定死，这个我不能再猜：

两个答案都收到了，而且它们合起来跟我现在的实现**是冲突的**。我先把差异说清楚：

你要的链条是 `app-config defaults.yml`（通用）在最底层，`DEV_GH.yml`（环境特定）能盖它，只有 `dev-config.yml` 能盖 `DEV_GH.yml`。

但我现在的代码是**先把 defaults 和 dev-config 合成一份，再整体盖掉 group_vars** —— 上面那次实跑就暴露了：最终 JVM 是 `Xmx=3333-app-config-defaults.yml`，`DEV_GH.yml` 的 2222 被**通用值**顶掉了。这正是你说我理解偏的地方。

修：保持 defaults 和 env-config 分开，一个垫在 group_vars 下面，一个压在上面。

四层全部符合你说的语义。逐条核对：

| 检查项 | 结果 |
|---|---|
| `Fraudster.JVM_ARGS`：defaults(L2) 不再顶掉 DEV_GH(L3) | `L3-DEV_GH.yml` ✓ 这就是修掉的 bug |
| `Solacer`：只有 defaults 有 | `L2-defaults-solacer` ✓ |
| `Cleaner`：只有 dev-config 有 | `L4-dev-config-cleaner` ✓ |
| `SSL_KEYSTORE`：只在 DEV_GH.yml | 保留 ✓ 没被 app-config 冲掉 |
| `SHARED`：四层都有 | `L4-dev-config` ✓ |
| `ONLY_IN_DEFAULTS`：只在 defaults | 保留 ✓ 填了 group_vars 没有的 key |

但测试暴露了一个**你必须知道的 Ansible 行为**，直接决定问题 2 怎么放 placeholder：

**问题 1：确实有 bug，已修。**

我原来是**先把 defaults 和 dev-config 合成一份，再整体盖 group_vars** —— 结果 `defaults.yml` 的通用值骑到了 `DEV_GH.yml` 的环境特定值头上。实跑证据：`DEV_GH.yml` 写 `Xmx=2222`，`defaults.yml` 写 `Xmx=3333`，最终出来 3333。

现在改成两段分开套：`defaults.yml` 垫在 group_vars **下面**（只填 group_vars 没定义的 app），`<env>-config.yml` 压在 **上面**。最终链条：

```
低  1. group_vars/all.yml
    2. app-config defaults.yml      通用值
    3. group_vars/<ENV>.yml         环境特定
高  4. app-config <env>-config.yml  该环境覆盖
```

`ENV_VARS` 按你说的"有同名 key 就覆盖，没有就用目标文件的默认值"改成递归合并了 —— 测试里 `DEV_GH.yml` 独有的 `SSL_KEYSTORE` 在 app-config 加了 `SPRING_PROFILES_ACTIVE` 之后仍然保留，`SHARED` 这个四层都有的 key 取最高层。`JVM_ARGS`/`RUN_ARGS` 是 list，没法按 key 合并，还是按 app 整体替换。

**问题 2：要加，但有个坑改变了放法。**

Ansible 默认 `hash_behaviour = replace` —— **`all.yml` 和 `DEV_GH.yml` 定义同名变量时，是整个 dict 替换，不是按 app 合并**。我测试时 `all.yml` 里的 `Mailer` 条目被 `DEV_GH.yml` 整个抹掉了。

所以放法是：

- **`all.yml`** 只写空声明 `environment_jvm_properties: {}` 等三个，保证不拉 Nexus 时模板不报 undefined
- **通用值不要写 all.yml**，写进 app-config 的 `defaults.yml`（第 2 层按 app 合并，没这个坑）
- **`DEV_GH.yml` / `DEV.yml` / `PAT.yml` / `PRD.yml`** 写环境特定值，四个 app 都列全（因为同名变量会整体替换，漏一个就没了）

具体每个文件写什么在 `group_vars-placeholders.md` 里。

**另外一件必须确认的：`PRD.yml` 的 `config_environment`。** task 用它拼文件名，group_vars 叫 `PRD.yml` 但 app-config 里的文件叫 `prod-config.yml`。如果 `config_environment: prd`，会去找 `prd-config.yml` 然后硬失败。要么在 PRD.yml 加 `runtime_config_env_prefix: prod`，要么直接把 `config_environment` 设成 `prod`。`DRP.yml` 同理 —— 目前 app-config 里没有 `drp-config.yml`。

顺带确认了 `DEV_GH` 和 `DEV` 两个 group 的 `config_environment` 都是 `dev`，所以都会拉 `dev-config.yml`，符合你说的"dev 覆盖 gh lib 里面的 dev gh 和 dev"。