可以。建议把它做成一个 organization-level reusable workflow，由各个 microservice 在 PR merge 成功后调用。

不过 Jira 里通常不是直接“把 ticket 从一个 Kanban board 移到另一个 board”。Board 本质上是基于 JQL filter 展示 issue；自动化一般通过：

1. 提取 Jira ticket number；
2. 将 ticket transition 到目标 status；
3. 如果目标 board 使用不同的 filter，再更新对应字段，例如 Team、Component、Fix Version 或自定义字段，让 ticket 出现在目标 board。

Jira board 的列实际映射到 workflow status，因此下面先实现最常见的 transition 到目标 board 对应的 status。

⸻

1. Common reusable workflow

在 common workflow repository 中创建：

.github/workflows/jira-ticket-transition.yml
name: Jira Ticket Transition
on:
  workflow_call:
    inputs:
      commit_message:
        description: PR merge commit message or PR title
        required: true
        type: string
      jira_base_url:
        description: Jira base URL, for example https://jira.company.com
        required: true
        type: string
      target_status:
        description: Jira target status name
        required: true
        type: string
      ticket_pattern:
        description: Regex used to extract the Jira ticket
        required: false
        default: '[A-Z][A-Z0-9]+-[0-9]+'
        type: string
    secrets:
      jira_username:
        required: true
      jira_token:
        required: true
jobs:
  transition-jira-ticket:
    name: Transition Jira ticket
    runs-on: ubuntu-latest
    steps:
      - name: Extract Jira ticket
        id: jira-ticket
        shell: bash
        env:
          COMMIT_MESSAGE: ${{ inputs.commit_message }}
          TICKET_PATTERN: ${{ inputs.ticket_pattern }}
        run: |
          set -euo pipefail
          ticket_key="$(
            printf '%s\n' "${COMMIT_MESSAGE}" |
            grep -oE "${TICKET_PATTERN}" |
            head -n 1 || true
          )"
          if [[ -z "${ticket_key}" ]]; then
            echo "::notice::No Jira ticket found in: ${COMMIT_MESSAGE}"
            echo "found=false" >> "${GITHUB_OUTPUT}"
            exit 0
          fi
          echo "Jira ticket detected: ${ticket_key}"
          echo "found=true" >> "${GITHUB_OUTPUT}"
          echo "ticket_key=${ticket_key}" >> "${GITHUB_OUTPUT}"
      - name: Get available Jira transitions
        if: steps.jira-ticket.outputs.found == 'true'
        id: transitions
        shell: bash
        env:
          JIRA_BASE_URL: ${{ inputs.jira_base_url }}
          JIRA_USERNAME: ${{ secrets.jira_username }}
          JIRA_TOKEN: ${{ secrets.jira_token }}
          JIRA_TICKET: ${{ steps.jira-ticket.outputs.ticket_key }}
          TARGET_STATUS: ${{ inputs.target_status }}
        run: |
          set -euo pipefail
          response="$(
            curl --fail-with-body \
              --silent \
              --show-error \
              --user "${JIRA_USERNAME}:${JIRA_TOKEN}" \
              --header "Accept: application/json" \
              "${JIRA_BASE_URL}/rest/api/3/issue/${JIRA_TICKET}/transitions"
          )"
          transition_id="$(
            jq -r \
              --arg target "${TARGET_STATUS}" \
              '.transitions[]
               | select(
                   (.to.name | ascii_downcase) ==
                   ($target | ascii_downcase)
                 )
               | .id' <<< "${response}" |
            head -n 1
          )"
          if [[ -z "${transition_id}" || "${transition_id}" == "null" ]]; then
            echo "::error::No available transition to status '${TARGET_STATUS}' for ${JIRA_TICKET}"
            echo "Available transitions:"
            jq -r '.transitions[] | "- \(.name) -> \(.to.name) [id=\(.id)]"' \
              <<< "${response}"
            exit 1
          fi
          echo "transition_id=${transition_id}" >> "${GITHUB_OUTPUT}"
      - name: Transition Jira ticket
        if: steps.jira-ticket.outputs.found == 'true'
        shell: bash
        env:
          JIRA_BASE_URL: ${{ inputs.jira_base_url }}
          JIRA_USERNAME: ${{ secrets.jira_username }}
          JIRA_TOKEN: ${{ secrets.jira_token }}
          JIRA_TICKET: ${{ steps.jira-ticket.outputs.ticket_key }}
          TRANSITION_ID: ${{ steps.transitions.outputs.transition_id }}
          TARGET_STATUS: ${{ inputs.target_status }}
        run: |
          set -euo pipefail
          payload="$(
            jq -n \
              --arg transition_id "${TRANSITION_ID}" \
              '{
                transition: {
                  id: $transition_id
                }
              }'
          )"
          curl --fail-with-body \
            --silent \
            --show-error \
            --user "${JIRA_USERNAME}:${JIRA_TOKEN}" \
            --request POST \
            --header "Accept: application/json" \
            --header "Content-Type: application/json" \
            --data "${payload}" \
            "${JIRA_BASE_URL}/rest/api/3/issue/${JIRA_TICKET}/transitions"
          echo "Successfully transitioned ${JIRA_TICKET} to ${TARGET_STATUS}"

这个 workflow 不硬编码 transition ID，而是先读取该 ticket 当前可执行的 transitions，再根据目标 status 名称查 ID。Jira 官方 API 提供了获取可用 transitions 和执行 transition 的 endpoints。

⸻

2. 当前 repository 的 caller workflow

例如：

.github/workflows/wbr-backend-merge-workflow.yml

在 merge workflow 成功之后添加：

jobs:
  build-and-merge:
    runs-on: ubuntu-latest
    steps:
      # Existing steps...
      - run: echo "Existing merge workflow"
  update-jira:
    name: Update Jira board
    needs: build-and-merge
    if: >-
      ${{
        needs.build-and-merge.result == 'success' &&
        github.event.pull_request.merged == true
      }}
    uses: TD-Universe/common-workflows/.github/workflows/jira-ticket-transition.yml@main
    with:
      commit_message: ${{ github.event.pull_request.title }}
      jira_base_url: https://jira.company.com
      target_status: Ready for Release
      ticket_pattern: 'WMPTRADE-[0-9]+'
    secrets:
      jira_username: ${{ secrets.JIRA_SERVICE_ACCOUNT_USERNAME }}
      jira_token: ${{ secrets.JIRA_SERVICE_ACCOUNT_TOKEN }}

GitHub reusable workflow 使用 workflow_call 定义 inputs/secrets，并由 caller job 通过 uses 调用；它不能放在普通 job 的 steps 下面。

⸻

3. 提取图片中的 ticket

图片中的 PR/commit message：

WMPTRADE-34173 Binary content derived from a content type (#980)

使用：

grep -oE 'WMPTRADE-[0-9]+'

输出：

WMPTRADE-34173

为了兼容其他 Jira project，推荐默认 regex：

[A-Z][A-Z0-9]+-[0-9]+

如果只允许 WMPTRADE：

WMPTRADE-[0-9]+

⸻

4. 获取真正的 PR commit message

截图中的 workflow 标题看起来很可能来自 PR title。最稳定的方式是直接传：

commit_message: ${{ github.event.pull_request.title }}

而不是依赖：

${{ github.event.head_commit.message }}

因为 head_commit 是否存在取决于触发事件，并且 squash、merge commit、rebase 对最终 commit SHA 和 commit message 的行为不同。GitHub 支持 merge commit、squash 和 rebase 三种合并方式。

推荐触发配置：

on:
  pull_request:
    types:
      - closed
    branches:
      - main

然后：

if: github.event.pull_request.merged == true

⸻

5. 如果真的是两个不同 Board

假设：

Board A filter:
project = WMPTRADE AND "Delivery Team" = WBR
Board B filter:
project = WMPTRADE AND "Delivery Team" = MobileB

那么仅 transition status 不够，还需要更新 "Delivery Team" custom field。可以在 common workflow 增加：

      jira_field_id:
        required: false
        type: string
      jira_field_value:
        required: false
        type: string

以及一个 update step：

      - name: Update Jira board routing field
        if: >-
          ${{
            steps.jira-ticket.outputs.found == 'true' &&
            inputs.jira_field_id != '' &&
            inputs.jira_field_value != ''
          }}
        shell: bash
        env:
          JIRA_BASE_URL: ${{ inputs.jira_base_url }}
          JIRA_USERNAME: ${{ secrets.jira_username }}
          JIRA_TOKEN: ${{ secrets.jira_token }}
          JIRA_TICKET: ${{ steps.jira-ticket.outputs.ticket_key }}
          FIELD_ID: ${{ inputs.jira_field_id }}
          FIELD_VALUE: ${{ inputs.jira_field_value }}
        run: |
          set -euo pipefail
          payload="$(
            jq -n \
              --arg field_id "${FIELD_ID}" \
              --arg value "${FIELD_VALUE}" \
              '{
                fields: {
                  ($field_id): $value
                }
              }'
          )"
          curl --fail-with-body \
            --silent \
            --show-error \
            --user "${JIRA_USERNAME}:${JIRA_TOKEN}" \
            --request PUT \
            --header "Accept: application/json" \
            --header "Content-Type: application/json" \
            --data "${payload}" \
            "${JIRA_BASE_URL}/rest/api/3/issue/${JIRA_TICKET}"

Caller：

with:
  commit_message: ${{ github.event.pull_request.title }}
  jira_base_url: https://jira.company.com
  target_status: Ready for Release
  jira_field_id: customfield_12345
  jira_field_value: MobileB

所以最终需要先确认目标效果属于哪一种：

同一个 Jira workflow 中移动 Kanban column
→ Transition status
从 WBR board 出现在 MobileB board
→ 更新 board filter 使用的字段，可能还要 transition status

另外，建议把 Jira credentials 放在 organization-level secrets 或 GitHub Environment 中，不要写进 YAML。Common workflow repository 可以在 organization 内共享 reusable workflows。