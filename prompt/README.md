# Copilot DevOps Kit v2（Java / Spring Boot / K8s / Ansible / GitHub Actions）

给 VS Code Copilot 用的一套仓库级配置，覆盖排错、写代码和部署后优化。v2 针对 **Opus 不可用** 的情况做了调整：主力换成 GPT-5.6 Sol，并把 Opus 自带的"判断力"尽量搬进配置和脚本里。

> 面向模型的文件（instructions / agents / skills / prompts）都用英文写：始终加载的内容用英文 token 更少、团队也能共用。说明文档用中文。

## v2 改了什么

| 改动 | 为什么 |
|---|---|
| 主力模型换成 **GPT-5.6 Sol**（triage / planner / coder） | 剩下的模型里，它在终端类和编码类评测上最强，和你的实际体验一致 |
| 新增 **critic** agent（Claude Sonnet 5）和 `/second-opinion` | 用另一个模型专门挑错，抓住 Sol 过早下结论的问题 |
| 新增 **bulk** agent（GPT-5.3-Codex） | 批量机械修改用更便宜的模型 |
| triage / planner 加入**证据纪律**：先列已读证据，结论必须引用 `path:line`，并先做一次反证检查 | 减少模型编造，弥补非 Opus 模型的判断力差距 |
| 新 skill **config-drift**：比对仓库渲染出的结果和集群实际状态 | DevOps 排错里最常见的误判，是把仓库里的配置当成了集群里实际跑的配置 |
| 新 skill **validate-changes**：按改动的文件自动选校验工具 | 让 linter 充当编译器，兜住较弱模型的错误 |
| 新 prompt **`/trace`**：逐跳追踪一个配置或请求，每一跳给出 `path:line` | 读懂代码时，逐跳追踪比让模型"解释整个模块"准确得多 |
| 移除所有 Opus 引用，更新价格表 | 适配你现在能用的模型 |

---

## 1. 安装

1. 把 `.github/` 和 `docs/ai/` 复制到仓库根目录。如果之前装过 v1，直接覆盖；如果你改过 `copilot-instructions.md` 或 `docs/ai/` 里的内容，先手工合并。
2. 给脚本加执行权限：`chmod +x .github/skills/*/scripts/*.sh`
3. 改掉所有 `TODO`：`grep -rn TODO .github docs/ai`。重点是各 instructions 文件里的 `applyTo` 路径，要改成你仓库的真实目录。
4. 安装本地工具。缺哪个，对应的检查会显示 SKIP，不会报错：
   `gh`（需先 `gh auth login`）、`kubectl`、`helm`、`kubeconform`、`ansible-lint`、`actionlint`、`yamllint`
5. 在 Chat 里跑一次 `/bootstrap-knowledge`，审核生成的 `docs/ai/*.md` 后提交。

## 2. 每个 agent 用什么模型、什么思考强度

思考强度（Thinking Effort）目前**只能在模型选择器里设**：点模型名旁边的 `>`。`.agent.md` 里设置思考强度的功能还没有被可靠支持，所以每个 agent 的正文第一行都写了建议值，切换 agent 时顺手调一下。

| Agent | 模型（按优先级） | 思考强度 | 用途 |
|---|---|---|---|
| triage | GPT-5.6 Sol → GPT-6.1 Sol | **High** | 排错，只读 |
| planner | GPT-5.6 Sol → GPT-6.1 Sol | **High** | 设计、多组件问题、`/trace` |
| coder | GPT-5.6 Sol → GPT-6.1 Sol | Medium（逻辑复杂时用 High） | 有界实现 + 校验 |
| critic | Claude Sonnet 5 → GPT-5.6 Sol | Medium | 第二意见，专门挑错 |
| bulk | GPT-5.3-Codex → GPT-5.6 Luna | Low | 重命名、批量改版本号等机械修改 |
| reviewer | GPT-5.6 Luna → Claude Haiku 4.5 | Low | 提交前审查 diff |

**管理员开通 GPT-6.1 Sol 之后**：把 triage、planner、coder 三个文件里 `model:` 的两项对调，让 6.1 排第一。

`model:` 里的名字必须和模型选择器里显示的**完全一致**。切换到某个 agent 后，看一眼选择器显示的模型对不对；不对就照着选择器里的名字改。

## 3. 确认真的生效了

| 检查 | 怎么看 |
|---|---|
| 全局 instructions | 随便问一句，展开回答上方的 References，应包含 `copilot-instructions.md` |
| 按文件 instructions | 打开一个 `.java` 文件再提问，References 里应出现 `java-spring.instructions.md` |
| Custom agents | agent 选择器里能看到 triage、planner、coder、critic、bulk、reviewer |
| Skills | 对 triage 说"CI 挂了"，应看到它读取 `ci-failure-triage/SKILL.md` 并运行脚本 |
| 证据纪律 | triage 的回答应以 **Evidence read:** 开头，并带 `path:line` |
| Prompt files | 输入 `/` 能看到 triage、trace、second-opinion、feature、handoff、optimize 等 |
| 工具 | 如果某个 agent 跑不了命令或改不了文件，用 Chat 里的工具配置界面重新勾选，以界面显示的名字为准 |

Skill 没触发：最常见的原因是你说的话和 `description:` 里的关键词对不上。把你习惯的说法（包括中文）加进 description；已经预置了几个，比如"流水线失败"、"pod 起不来"、"配置不一致"。

## 4. 文件一览

```
.github/
├── copilot-instructions.md            # 始终加载：仓库是什么、工作方式、证据规则、硬性禁区
├── instructions/                       # 打开对应文件时才加载（Java、测试、K8s、Ansible、Actions）
├── agents/
│   ├── triage.agent.md     # 排错，只读，证据纪律 → 交接给 critic / coder / planner
│   ├── critic.agent.md     # 用另一个模型挑错，只读
│   ├── planner.agent.md    # 设计、追踪，只读 → 交接给 critic / coder
│   ├── coder.agent.md      # 有界实现，每轮修改后都跑 validate → 交接给 reviewer
│   ├── bulk.agent.md       # 机械批量修改，用便宜模型
│   └── reviewer.agent.md   # 提交前审查 git diff
├── skills/
│   ├── ci-failure-triage/          只取失败 step 的日志，并和上一次成功的运行比对
│   ├── k8s-pod-debug/              一次性 pod 快照
│   ├── config-drift/        (新)   仓库渲染结果 vs 集群实际状态；helm 历史；镜像和环境变量名
│   ├── validate-changes/    (新)   按改动的文件自动选择 actionlint / helm+kubeconform / ansible-lint / yamllint / 编译
│   ├── spring-boot-startup-debug/  抽取 FAILED TO START 和最深一层的 Caused by，含 SSL/keystore 映射
│   ├── ansible-debug/              syntax-check → lint → 单主机 --check --diff，以及变量实际值
│   ├── java-test-runner/           Maven/Gradle 自动识别，只输出失败摘要
│   ├── repo-knowledge/             生成或刷新 docs/ai 知识包
│   └── post-deploy-review/         部署后评审，输出排好优先级的优化清单
└── prompts/
    /triage  /trace  /second-opinion  /feature  /optimize  /handoff  /known-issue  /bootstrap-knowledge
docs/ai/   ARCHITECTURE.md · REPO_MAP.md · KNOWN_ISSUES.md
```

## 5. 日常工作流

**排错**
`/triage`，并用 `#file` 附上该环境的 values 文件和报错 → triage 跑 skill 脚本取证，需要时跑 config-drift → 给出带引用的假设和反证检查结果 → 对结论没把握时点 **Second opinion** → 确认后点 **Fix it** → coder 修改并跑 validate → `/known-issue` 记录下来。

**读懂代码**
`/trace server.ssl.key-store in dev` 或 `/trace POST /orders` → 得到一条逐跳的 `path:line` 链；标了 **(gap)** 的地方就是还需要补查的。

**写代码**
`/feature` → planner 出分步计划 → 点 **Second opinion** 让 critic 挑风险 → 点 **Implement step 1** → coder 修改，跑 validate 和窄测试 → 点 **Review diff** → 下一步开**新会话**。

**部署后优化**
`/optimize` → 拿 pod 快照、漂移检查结果、监控指标和 CI 历史 → 输出按影响和成本排序的优化表 → 前 3 项交给 `/feature` 做计划。

**线程变长时**
超过 8–10 轮，或者开始重复同样的猜测，就用 `/handoff` 压缩成摘要，再开新会话。模型选择器里显示的 "1M" 是上下文上限，不是建议用满；上下文越长越乱，非 Opus 模型掉质量更快。

## 6. 价格与 credit 预算

价格来自 GitHub 官方定价页（2026 年 10 月版，每 100 万 token，1 credit = $0.01）。使用前请在定价页核对最新价格。

| 模型 | 状态 | 输入 | 缓存输入 | 输出 | 典型会话约 credits* |
|---|---|---|---|---|---|
| GPT-5.6 Sol | 可用 | $4.00 | $0.40 | $20.00 | ~100 |
| **GPT-6.1 Sol** | **需管理员开通** | $2.00 | $0.10 | $10.00 | ~50 |
| Claude Sonnet 5 | 可用 | $2.00 | $0.20 | $10.00 | ~50 |
| GPT-5.3-Codex | 可用 | $1.75 | $0.175 | $14.00 | ~60 |
| Claude Haiku 4.5 | 可用 | $1.00 | $0.10 | $5.00 | ~25 |
| GPT-5.6 Luna | 可用 | $0.20 | $0.02 | $1.20 | ~6 |

\* 假设一个会话累计 40 万输入 token（其中 75% 命中缓存）、2.5 万输出 token，未计入缓存写入费用。这只是数量级估算，以账单页的实际数字为准。

**GPT-6.1 Sol 的价格只有 GPT-5.6 Sol 的一半，而且是更新一代的模型**，是最值得找管理员开通的一个。可以直接发给管理员：

> Could you enable GPT-6.1 Sol (and Claude Sonnet 5.5) for Copilot? GPT-6.1 Sol is listed at $2/$10 per 1M tokens vs $4/$20 for GPT-5.6 Sol, which I currently use for troubleshooting, so it should lower our AI credit spend while improving results. Since Opus was removed, Sol is the only model that handles our DevOps debugging well.

如果公司和 Anthropic 或 OpenAI 有 API 合同，还可以请管理员开启 **BYOK（自带 API key）** 策略。Business/Enterprise 版需要管理员开启后，才能在 VS Code 里接入自有的模型。

上线后的调优步骤见 [ROADMAP.md](ROADMAP.md)。
