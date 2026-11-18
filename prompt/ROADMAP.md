# 上线后的优化计划（v2）

配置放进仓库只是开始。没有 Opus 之后，效果主要取决于两件事：给模型的证据质量，以及你把判断沉淀进配置的速度。

---

## 阶段 0：第 1 天，装好并跑通

- [ ] 按 README 安装，清掉所有 `TODO`，确认 `applyTo` 路径正确
- [ ] 逐项完成 README "确认真的生效了" 的检查
- [ ] 把模型选择器里的模型名和各 agent 的 `model:` 核对一遍
- [ ] 把 README 第 6 节的消息发给管理员，申请开通 GPT-6.1 Sol 和 BYOK
- [ ] 跑 `/bootstrap-knowledge`，**亲自审改**所有标了 `(inferred)` 的内容后提交
- [ ] 把最近 3–5 次真实故障补进 `KNOWN_ISSUES.md`（凭记忆写也行）
- [ ] 在一个 dev 服务上分别跑一次 `config-drift` 和 `validate-changes`，确认脚本能在你的环境里正常工作

**完成标准**：问"orders-svc 的配置从哪来、怎么部署到 dev"，agent 引用 `ARCHITECTURE.md` 和 `path:line` 来回答，而不是在全仓库里搜。

## 阶段 1：第 1–2 周，建立基线

准备一个**固定测试集**：从 `KNOWN_ISSUES.md` 里挑 5 个已经知道答案的问题，并保留当时的报错和日志。用它来比较不同配置、不同模型的效果，比凭感觉判断可靠得多。

每次用 Copilot 处理一件事，花 20 秒记一行（放在个人笔记里，不必进仓库）：

| 日期 | 任务类型 | agent | 模型/思考强度 | credits | 首要假设对吗？ | 轮数 | critic 意见 | 不好的地方 |
|---|---|---|---|---|---|---|---|---|
| 11-18 | Pod 起不来 | triage | Sol 5.6 / High | 85 | 是 | 3 | Agree | — |
| 11-18 | SSL 配置 | triage | Sol 5.6 / High | 120 | 否 | 7 | Disagree（读错了环境的 values） | 没跑 config-drift |

两周后看四个数字：

1. **首要假设命中率**：triage 第一轮给出的首要假设是否正确
2. **critic 的有效分歧率**：critic 说 Disagree 且事后证明它对的比例。这个比例高，说明第二意见值得常用；接近 0，就只在没把握时才用
3. **每个已解决问题花了多少 credits**
4. **回答带引用的比例**：没有 `path:line` 的结论有多少

## 阶段 2：第 3–4 周，根据记录调优

| 现象 | 调整 |
|---|---|
| 同一个纠正说了两次 | 写进对应的 `*.instructions.md` |
| 某类故障反复出现 | 新建一个 skill，带上采集脚本 |
| skill 该触发没触发 | 把你实际的说法（包括中文）加进 `description` |
| agent 总在全仓库乱搜 | `ARCHITECTURE.md` 或 `REPO_MAP.md` 缺了对应信息，补上 |
| 结论经常读错环境 | 在 `ARCHITECTURE.md` 的环境表里写清每个环境对应的 values 文件 |
| 回答经常不带引用 | 检查 triage 是否被选中；必要时把证据纪律在提问时再强调一句 |
| coder 越界改文件 | 收紧 coder 的规则，或在计划里写死文件清单 |
| critic 总是附和 | 把 critic 换成 Sol，或者在提问时明确它需要检查的环节 |
| reviewer 用 Luna 漏掉明显问题 | 换成 Haiku 4.5，再观察一周 |
| `copilot-instructions.md` 超过 50 行 | 把不是全局性的内容下沉到 `applyTo` instructions 或 skill |

**原则**：一次只改一处，用固定测试集验证后再改下一处，否则分不清是哪个改动起的作用。

## 阶段 3：第 2 个月，护栏与外部上下文

1. **用 hooks 把"禁止"变成确定性的拦截**。目前"不准 `kubectl apply`、`helm upgrade`"只是写在 instructions 里，模型不一定遵守。VS Code 和 Copilot 支持在工具调用前执行 hook：写一个脚本，遇到 `kubectl (apply|delete|edit|scale)`、`helm (upgrade|uninstall)`，或者不带 `--check` 的 `ansible-playbook` 时直接拒绝。还可以在编辑后自动运行 `validate.sh`。具体字段以你所用版本的 hooks 文档为准。
2. **接只读 MCP，拿仓库以外的证据**（需公司批准）：
   - GitHub MCP：PR、Issue、Actions 运行记录
   - Prometheus / Grafana：让 `/optimize` 直接取 p95 指标，不用你手动粘贴
   - 日志平台：按 traceId 查日志
   每个 MCP 只开读权限，并且只加到需要它的 agent 的 `tools:` 里。
3. **推广给团队**：通过 PR 合入仓库；个人偏好放在 `~/.copilot/skills/` 等个人目录，不污染仓库。

## 阶段 4：持续，保鲜与回归

- **管理员开通新模型时**（比如 GPT-6.1 Sol）：用固定测试集分别跑旧模型和新模型，比较命中率和 credits，再决定是否调整 `model:` 的顺序
- **每季度**：跑一次 `repo-knowledge` 的 Refresh；删掉过时的 `KNOWN_ISSUES` 条目
- **每月看一次账单**：如果 credits 突然升高，先检查是否有超长线程没用 `/handoff`，或者某个 instructions 文件变大了

---

## 一页纸版：每天的习惯

1. 新问题开新会话，用 `/triage`、`/trace` 或 `/feature` 开头
2. 用 `#file` 附上该环境的 values 文件和报错，不要让 agent 自己去猜
3. 排错用 Sol 加 High 思考强度；先让脚本取证，再让模型推理
4. 涉及集群配置时，先跑 config-drift
5. 对结论没把握时，点 **Second opinion**
6. 每轮修改后都跑 `validate.sh`，以 linter 的结果为准
7. 线程超过 10 轮左右就 `/handoff`，开新会话
8. 修好了就 `/known-issue`；同一个纠正说第二次，就写进 instructions
