好几种办法,从最安全到最接近真实逐层递进。核心原则:先在本地/隔离环境验证,别直接推到会挡所有人 PR 的 required check 上。

## 1. 本地跑,手动喂环境变量(最快)

这个脚本靠环境变量驱动,本地直接 export 就能跑,不用碰 GitHub。

```bash
export PROJECT_NAME="TD-Universe/wbr-ghrunner-libs"
export PROJECT_REF_NAME="123"          # 一个真实存在的 PR number
export GH_TOKEN="ghp_xxx"              # 你的 PAT
export JIRA_BASE_URL="https://track.td.com"
export JIRA_TOKEN="xxx"

python -c "from wbr_actions.validate_jira_in_commit import validate_jira_in_commit; validate_jira_in_commit()"
```

分别用"有真实 ticket 的 PR""ticket 格式对但不存在的 PR""完全没 ticket 的 PR"跑三次,看是否符合预期(前者正常返回,后两者 raise Exception)。前提是本地能连到 `track.td.com`(内网的话得挂 VPN 或在能触达的机器上跑)。

## 2. 单独把 `jira_ticket_exists` 拎出来测

不想跑整个 PR 流程,只想确认 API 这段对不对:

```bash
python -c "
import os
from wbr_actions.validate_jira_in_commit import jira_ticket_exists
print('real ticket:', jira_ticket_exists('WMPTRADE-32454'))   # 期望 True
print('fake ticket:', jira_ticket_exists('WMPTRADE-999999'))  # 期望 False
"
```

这一步能单独验证认证方式(Bearer vs Basic)、API 路径(/api/2 vs /api/3)、内网可达性这几个最容易踩坑的点,不受 PR 逻辑干扰。

## 3. 新建一个独立 workflow 文件,只在你的分支上触发

不要动现有的 required check。新建一个临时 workflow,限定只在你的 feature 分支跑,这样绝不影响别人:

```yaml
name: TEST JIRA precheck
on:
  pull_request:
    branches-ignore: []   # 或用 paths / 手动触发
  workflow_dispatch:       # 允许手动点按钮触发,最可控
jobs:
  test-validate-jira:
    runs-on: self-hosted   # 内网 JIRA 必须 self-hosted
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: test validate
        env:
          JIRA_BASE_URL: https://track.td.com
          JIRA_TOKEN: ${{ secrets.JIRA_TOKEN }}
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: python -c "from wbr_actions.validate_jira_in_commit import validate_jira_in_commit; validate_jira_in_commit()"
```

`workflow_dispatch` 让你能在 Actions 页手动点触发,反复调试而不用一直推 commit。关键:**这个 workflow 不加进 branch protection 的 required checks**,所以它红了也不会挡任何人合并,纯观察用。

## 4. 开一个 draft PR 专门测

用你截图里那个 `feature/WMPTRADE-32454-JIRA-commit-check` 分支开个 **draft PR**。draft 状态下即使有 check 也不能合并,天然隔离。在这个 PR 里故意构造几个 commit:一个带真 ticket、一个带假 ticket、一个不带,看新 workflow 的 check 结果是否逐个符合预期。

## 推荐路径

先 2(单测 API 函数,排掉认证/网络问题)→ 再 1(本地全流程)→ 最后 3 或 4(在真实 runner 上验证内网可达性和 checkout 行为)。等三层都绿了,再把它设为 required check 替换老的。

## 一个容易忽略的点

第 1、2 步在你自己机器上跑,如果 `track.td.com` 是内网,你本地不一定连得通——那 `jira_ticket_exists` 会走进 fail-open 分支返回 True,你会误以为"验证通过"其实是"没连上被放行"。判断办法:临时把 fail-open 那两个 `return True` 改成 `return False` 或打印状态码,确认你真的收到了 200/404,而不是异常兜底。测完记得改回来。

要哪一步的更完整脚本,我可以展开。