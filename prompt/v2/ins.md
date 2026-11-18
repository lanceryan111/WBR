你现在已经完成了 Copilot 优化的第一阶段：User-level Instructions + 专门的 RCA Prompt。

下一步，我不建议继续无目的地增加 Instructions，而是建立一套可衡量的优化方法，让现有模型在你的 DevOps 工作中尽可能接近以前 Claude Opus 的表现。

我认为最值得优化的是以下五个能力：

Root Cause Analysis 准确性

最重要

跨文件理解与依赖追踪

第二优先

最小化、安全的代码修改

第三优先

验证能力与防止 Regression

第四优先

上下文管理与效率

第五优先

上面是建议的优化优先级，不是模型性能测量结果。

尤其是你遇到过的 AutoSys 手动部署与 Pipeline 冲突、GitHub Actions Reusable Workflow、Ansible 配置差异等问题，非常适合用来验证模型的真实能力。

## 1. 用真实问题建立模型评测体系

我建议你先选 3 个以前遇到过、现在已经知道正确答案的问题。

| 测试                     | 考察能力          | 权重  |
| ---------------------- | ------------- | --- |
| AutoSys Agent 部署冲突     | RCA、环境差异、配置追踪 | 40% |
| GitHub Actions 多文件调用   | 依赖追踪、代码理解     | 30% |
| Bash / Ansible Bug Fix | 代码修改、测试、回归风险  | 30% |

对每个测试，记录以下五项指标。

## Copilot RCA 评测卡

每项按 0–5 分打分，按权重计算总分。

Root Cause 准确性

35%

有没有找到真实原因，而不只是解释报错

0/5

Evidence Quality

20%

是否提供准确文件路径、代码位置和日志证据

0/5

Cross-file Reasoning

20%

是否追踪 Workflow、Script、Config 之间的关系

0/5

Fix Quality

15%

是否最小化修改，避免破坏已有逻辑

0/5

Validation

10%

是否提供可以实际执行的验证步骤

0/5

总分

# 0/100

分析评分

每个案例都用同样的输入、同样的模型、同样的上下文进行前后对比。不要同时更改模型、Reasoning Effort 和 Instructions，否则无法判断是什么带来了改善。

## 2. 我建议再增加 3 条高价值 Instructions

这三条可以直接追加到你的 `~/.copilot/copilot-instructions.md`，但先确认没有与现有规则重复。

### A. 强制 Evidence-based Reasoning

解决模型看了几个文件就猜测 Root Cause 的问题。

```

## Evidence-Driven Investigation

- Do not conclude a root cause based solely on an error message.
- Trace the relevant execution path before drawing conclusions.
- For each root cause hypothesis, identify supporting evidence and missing evidence.
- Cite actual file paths, functions, and log entries when available.
- Never invent file references, code behavior, or test results.
- If the root cause cannot be confirmed, state what evidence is needed.
- Prefer the simplest hypothesis consistent with all verified evidence.

```

### B. 强制 Change Impact Analysis

解决模型修复一个问题，却破坏其他 Pipeline 的问题。

```

## Change Impact Analysis

Before modifying code:

- Identify all relevant callers and downstream dependencies.
- Determine whether the component is shared across applications.
- Identify environment-specific configuration differences.
- Check existing interfaces, parameters, and output contracts.
- Explain the expected impact of the proposed change.
- Prefer minimal diffs over broad refactoring.
- Do not modify unrelated files.
- Request approval before changing shared or production-critical behavior.

```

### C. 强制验证，而不是自称已经修好

```

## Verification Standards

After implementing a change:

- Run relevant safe validation commands when available.
- Distinguish tests actually executed from tests merely recommended.
- Report the exact validation commands and their results.
- Do not claim success without verification evidence.
- Inspect the final diff for unintended changes.
- Identify remaining risks and untested scenarios.
- Never run deployment, destructive, or production-changing commands without approval.

```

其中 Change Impact Analysis 对你的工作可能最有价值，因为 GitHub Actions、Reusable Workflow、Ansible Roles 和 Salt Formula 经常被多个应用或环境共享。

## 3. 还有一个比增加 Instructions 更有效的优化：Context Engineering

VS Code 官方最新文档也强调，Instructions 应该简短、具体、可执行，而不是越多越好。更重要的是让 Agent 获得正确的上下文，并用实际结果检验。

[image](https://www.google.com/s2/favicons?domain=https://code.visualstudio.com\&sz=32)

Visual Studio Code+1



例如你要调查一个 Pipeline Failure，不要只输入：

> Why is this pipeline failing?

可以改成：

Investigate the failure in this GitHub Actions pipeline.

**Observed behavior:** The deployment failed during the AutoSys agent installation.

**Expected behavior:** The pipeline should install the agent consistently with the existing DEV deployment.

**Scope:** Inspect the relevant workflow, reusable actions, Ansible/Salt configuration, and deployment scripts.

**Constraints:**

- Investigation only; do not modify files.
- Check whether previous manual deployment caused configuration drift.
- Distinguish confirmed evidence from hypotheses.
- Identify the smallest safe fix and how to validate it.

Use the repository context and existing instructions.

这类 Prompt 给模型明确的目标、实际症状和调查边界，比单纯要求它“think harder”更有效。

## 4. 你还应该检查一个重要设置：Agent Harness

从你之前的截图来看，你的 VS Code Chat 处于 `Local` 模式。

我刚查了 VS Code 官方文档，有一个值得提前注意的变化：

Local Harness 计划于 2027 年 2 月移除，官方建议逐步迁移到 Copilot Harness。 现有 `.prompt.md` 文件主要用于 Local Harness，而 Copilot Harness 更推荐用 Agent Skills 承载可复用的工作流程。

[image](https://www.google.com/s2/favicons?domain=https://code.visualstudio.com\&sz=32)

Visual Studio Code



所以你现在可以继续使用已经配置好的 `/rca`，但暂时不建议再建立大量 Prompt Files。下一阶段可以考虑把 RCA Workflow 转成 Skill，避免将来迁移时重新配置。

## 5. 我建议你的下一步行动

第一步：保留当前配置作为 Baseline

先保存现有 Instructions 的副本，选一个已知 Root Cause 的故障，记录模型表现。

第二步：优先测试 Evidence + Impact Analysis

只增加一组针对当前弱点的规则，重新测试同一个案例。

第三步：比较 GPT-5.6 Sol 和 GPT-5.3-Codex

使用相同任务、相同 Instructions 和相同 Agent 权限，记录准确率、修改质量、耗时和资源消耗。

第四步：针对重复出现的错误继续优化

例如模型经常忽略 Reusable Workflow，就增加具体的依赖追踪规则；如果经常修改无关文件，就加强 Change Scope 约束。

### 我最想帮你进一步优化的一点

你现在的 Instructions 已经涵盖不少原则，但原则不等于实际执行流程。

例如：

`Trace dependencies before editing`

这句话虽然正确，但没有规定模型具体应该检查哪些依赖、什么时候停止调查、如何证明调查完成。

如果你愿意，下一步可以把你目前的 `copilot-instructions.md`、`devops-troubleshooting.instructions.md` 和 `rca.prompt.md` 三份内容发给我。

我可以帮你做一次 Instruction Audit，重点检查重复规则、冲突、过度约束、缺少可验证的执行步骤，以及哪些规则应该放在 Global Instructions、哪些应该移到 RCA Workflow。

这样比继续盲目增加规则，更有机会真正改善现有模型的代码理解和 Troubleshooting 表现。

2. 最推荐的修改：精简 Global Instructions
我建议把 ~/.copilot/copilot-instructions.md 中关于完整 RCA、全面检查依赖、验证所有环境等要求移到专用 Prompt。

Global 只保留：

# Global Engineering Instructions

- Follow existing repository conventions.
- Read directly relevant code before proposing changes.
- Prefer minimal and targeted modifications.
- Do not invent variables, APIs, configuration, or test results.
- Distinguish verified facts from assumptions.
- Avoid repeating identical searches or file reads without a new question.
- If two consecutive investigation steps provide no new evidence, stop expanding the search and summarize findings.
- Do not run destructive commands or modify production systems without approval.
- Match investigation depth to task complexity.



这里最重要的是最后一条：

Match investigation depth to task complexity.

模型解释一个 YAML 变量，不应该被迫调查整个 Repository
