会自动应用，不需要每次 Prompt 都 `@`！

只要你把之前的内容放在正确的位置，VS Code GitHub Copilot 就会自动读取并应用这些 Instructions。

不过，Copilot 有几种不同的 Instructions 机制，适用范围不一样。针对你的 DevOps 工作，我建议采用 Global Instructions + Repository Instructions + File-specific Instructions 三层配置。

## 1. Copilot Instructions 有什么区别？

| 类型                         | 文件位置                                     | 是否自动应用               |
| -------------------------- | ---------------------------------------- | -------------------- |
| Repository Instructions    | `.github/copilot-instructions.md`        | &#x20;自动应用于该项目       |
| File-specific Instructions | `.github/instructions/*.instructions.md` | &#x20;匹配文件时自动应用      |
| Global Instructions        | VS Code User Settings / Profile          | &#x20;根据配置应用于所有项目    |
| Prompt Files               | `.github/prompts/*.prompt.md`            | &#x20;通常需要手动调用       |
| Agent Files                | `.github/agents/*.agent.md`              | &#x20;通常需要选择对应 Agent |

例如：

```
my-devops-repo/
├── .github/
│   ├── copilot-instructions.md
│   ├── instructions/
│   │   ├── github-actions.instructions.md
│   │   ├── ansible.instructions.md
│   │   └── shell.instructions.md
│   └── prompts/
│       └── troubleshoot.prompt.md
├── .github/workflows/
├── ansible/
└── scripts/
```

关键区别： `copilot-instructions.md` 是项目级规则，而 `*.instructions.md` 可以通过 `applyTo` 指定适用的文件范围。自动加载不等于每次都保证严格遵守，因此重要操作仍然需要人工确认。

## 2. 我最推荐你额外添加的 4 类 Instructions

你目前最大的问题是模型容易误判、乱改代码、忽略现有设计。因此我建议添加以下四类规则，而不是单纯增加模型的角色描述。

### A. GitHub Actions / CI/CD

文件：`.github/instructions/github-actions.instructions.md`

```

---
description: "GitHub Actions workflow and CI/CD pipeline rules"
applyTo: ".github/workflows/**/*.yml,.github/workflows/**/*.yaml"
---

# GitHub Actions Standards

- Trace reusable workflows, composite actions, scripts, and dependencies before making changes.
- Preserve existing branch triggers, environment mappings, and artifact publishing rules.
- Never invent repository secrets, environment variables, or runner labels.
- Check job dependencies, permissions, conditional execution, and artifact paths.
- Consider differences between self-hosted macOS and Linux runners.
- Avoid introducing new third-party actions without approval.
- Make minimal changes and explain the impact on existing pipelines.
- Validate YAML and workflow structure where tooling is available.

```

### B. Ansible / Salt / Deployment

文件：`.github/instructions/deployment.instructions.md`

```

---
description: "Ansible, SaltStack and deployment automation rules"
applyTo: "**/*.sls,**/*.j2,**/playbooks/**/*.yml,**/playbooks/**/*.yaml,**/roles/**/*.yml,**/roles/**/*.yaml"
---

# Deployment Automation Standards

- Identify the target environment and deployment method before changing configuration.
- Check idempotency and existing resource state.
- Never assume an environment is clean.
- Detect possible configuration drift from manual deployments.
- Preserve existing formulas, roles, and pillar/inventory structure.
- Do not modify production settings without approval.
- Consider permissions, service dependencies, rollback, and failure recovery.
- Prefer safe validation or dry-run commands where supported.
- Explain potential impact on DEV, PAT, and PROD separately.

```

这里特别适合你之前遇到的 AutoSys 手动安装与 Pipeline 安装冲突问题。

### C. Bash / Python Code Quality

文件：`.github/instructions/scripts.instructions.md`

```

---
description: "Bash and Python script development standards"
applyTo: "**/*.sh,**/*.bash,**/*.py"
---

# Script Development Standards

- Read the complete relevant function and its callers before editing.
- Preserve existing interfaces, arguments, exit codes, and output contracts.
- Never suppress errors without explaining why.
- Avoid unnecessary refactoring.
- Handle quoting, whitespace, paths, and empty variables safely.
- Avoid logging secrets or credentials.
- Consider compatibility with existing OS and runtime versions.
- Validate with shellcheck, bash -n, Python compile checks, or relevant tests when available.
- Summarize changes and possible regressions.

```

### D. Root Cause Analysis / Troubleshooting

这类规则适用于任何文件，建议放到之前的 `.github/copilot-instructions.md` 中，而不是另建一个始终加载的文件。

```

# Troubleshooting Principles

- Investigate before proposing a fix.
- Trace the actual execution path rather than assuming intended behavior.
- Correlate errors with relevant code, configuration, dependencies, and deployment history.
- Distinguish the triggering error from the underlying root cause.
- Do not claim a root cause is confirmed without supporting evidence.
- Consider environmental differences and configuration drift.
- Rank hypotheses by evidence and propose tests to distinguish them.
- If multiple explanations are plausible, do not prematurely choose one.
- Do not modify code during the investigation phase.
- Ask for missing evidence only after checking available repository context.

```

## 3. 再加一个我认为特别有价值的 Prompt File

除了自动 Instructions，我还建议你创建一个专门的 Troubleshooting Prompt：

`.github/prompts/rca.prompt.md`

这样每次遇到复杂问题，不用重新写很长的 Prompt，直接在 Copilot Chat 输入 `/rca` 即可调用。

```

---
description: "Investigate CI/CD failures without modifying files"
agent: "agent"
---

Investigate the current issue as a senior DevOps engineer.

First inspect the relevant repository context, execution flow,
configuration, dependencies, and available logs.

Do not edit files or execute deployment commands.

Provide:

1. Observed failure and affected components
2. Execution flow and dependencies
3. Verified evidence with file paths and line references
4. Root cause or ranked hypotheses
5. Evidence supporting and contradicting each hypothesis
6. Minimal proposed fix
7. Safe validation and rollback plan

Do not present assumptions as facts.
Do not implement anything until I approve.

```

Prompt Files 是手动调用的，与自动加载的 Instructions 不同。

[image](https://www.google.com/s2/favicons?domain=https://code.visualstudio.com\&sz=32)

code.visualstudio.com+1



## 4. 如何确认 Copilot 真的读取了 Instructions？

在 VS Code：

1. 保存 `.github/copilot-instructions.md`。
2. 新开一个 Copilot Chat。
3. 选择你当前使用的 Copilot Agent。
4. 输入 `Which custom instructions are currently applied to this request?`
5. 查看回答的 References 或上下文信息，确认 Instructions 文件是否被引用。

还可以通过 `Cmd + Shift + P` 搜索 `Chat: Open Customizations`，检查当前 Agent 可发现的配置文件。不同版本及 Agent Harness 的显示方式可能不同。

[image](https://www.google.com/s2/favicons?domain=https://code.visualstudio.com\&sz=32)

code.visualstudio.com+1



额外提醒： 如果你只是从 Claude Sonnet 5 切换到 GPT-5.6 Sol，但仍然使用同一个 Copilot Agent Harness，通常不需要重新设置 Instructions。更换底层模型不等于更换 Agent Harness。

## 5. 我建议你的最终配置

推荐的 Repository 结构

📁 .github/\
├── 📄 copilot-instructions.md\
│     └── 通用规则 + RCA 原则\
├── 📁 instructions/\
│   ├── github-actions.instructions.md\
│   ├── deployment.instructions.md\
│   └── scripts.instructions.md\
└── 📁 prompts/\
&#x20;   └── rca.prompt.md

通用规则保持简短；技术规则按文件类型加载；复杂故障调查通过 /rca 主动触发。

我建议先实施这五个文件，再用你已经知道正确答案的 Pipeline 故障测试效果。Instructions 越多不一定越好，太多重复甚至冲突的规则反而会降低模型的可靠性。

另外，如果这些规则只是你个人的偏好、不适合团队所有开发者，建议使用 VS Code 的 User-level Instructions；如果是整个团队都认可的工程规范，再提交到 Repository。

参考：[VS Code 官方 Custom Instructions 文档](https://code.visualstudio.com/docs/agent-customization/custom-instructions?utm_source=chatgpt.com)。
