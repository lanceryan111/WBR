你的实际需求已经不只是一个 curl：

1. 从 PR title / merge commit message 提取 WMPTRADE-xxxxx
2. 查询当前 Jira status
3. 获取当前状态可用的 transitions
4. 找到目标为 QA 的 transition
5. 执行 transition
6. Assign 给指定 QA
7. 处理已经在 QA、找不到 ticket、无可用 transition、用户不存在等情况

我的建议

使用 reusable workflow + Python script。

Caller workflow
    ↓
Reusable workflow
    ↓
Python script
    ├── extract Jira key
    ├── resolve transition
    ├── transition to QA
    └── assign QA user

Shell 比较适合只有一两个固定 API call 的场景。但你这个功能会成为 common action，并被多个 microservice 调用，Python 在 JSON 解析、异常处理、单元测试、日志和后续扩展方面明显更合适。

Jira 的 status 不能通过直接修改 status 字段完成，必须查询当前 issue 可用的 transitions，再调用 transition API；而且同一个目标状态从不同初始状态进入时，transition ID 可能不同。Jira Data Center 的 transition API 也支持在执行 transition 时同时设置可更新字段。

⸻

推荐目录结构

common-github-actions/
├── .github/
│   └── workflows/
│       └── transition-jira-to-qa.yml
├── scripts/
│   └── transition_jira_to_qa.py
└── tests/
    └── test_transition_jira_to_qa.py

你可以把它放在 common workflow repo，然后各 microservice 使用 reusable workflow 调用。GitHub 支持在 organization 内共享 reusable workflow。

⸻

1. Python script

scripts/transition_jira_to_qa.py

考虑到图片里的地址是公司内部 track.td.com，更像 Jira Server/Data Center，所以示例使用：

/rest/api/2

而不是 Jira Cloud 的 /rest/api/3。

#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any
import requests
from requests.auth import HTTPBasicAuth
DEFAULT_TICKET_PATTERN = r"\b[A-Z][A-Z0-9]+-\d+\b"
class JiraAutomationError(RuntimeError):
    """Raised when the Jira automation cannot complete safely."""
@dataclass(frozen=True)
class JiraConfig:
    base_url: str
    username: str
    token: str
    verify_ssl: bool = True
    timeout_seconds: int = 30
class JiraClient:
    def __init__(self, config: JiraConfig) -> None:
        self.base_url = config.base_url.rstrip("/")
        self.timeout_seconds = config.timeout_seconds
        self.session = requests.Session()
        self.session.auth = HTTPBasicAuth(
            config.username,
            config.token,
        )
        self.session.verify = config.verify_ssl
        self.session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> requests.Response:
        url = f"{self.base_url}{path}"
        response = self.session.request(
            method=method,
            url=url,
            timeout=self.timeout_seconds,
            **kwargs,
        )
        if response.ok:
            return response
        response_body = response.text[:2000]
        raise JiraAutomationError(
            f"Jira API request failed: "
            f"{method} {path}, "
            f"status={response.status_code}, "
            f"response={response_body}"
        )
    def get_issue(self, issue_key: str) -> dict[str, Any]:
        response = self._request(
            "GET",
            f"/rest/api/2/issue/{issue_key}",
            params={"fields": "status,assignee,summary"},
        )
        return response.json()
    def get_transitions(self, issue_key: str) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"/rest/api/2/issue/{issue_key}/transitions",
        )
        payload = response.json()
        return payload.get("transitions", [])
    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
    ) -> None:
        self._request(
            "POST",
            f"/rest/api/2/issue/{issue_key}/transitions",
            json={
                "transition": {
                    "id": transition_id,
                }
            },
        )
    def assign_issue(
        self,
        issue_key: str,
        qa_username: str,
    ) -> None:
        self._request(
            "PUT",
            f"/rest/api/2/issue/{issue_key}/assignee",
            json={
                "name": qa_username,
            },
        )
def extract_jira_ticket(
    source_text: str,
    pattern: str,
) -> str | None:
    match = re.search(pattern, source_text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(0).upper()
def normalize(value: str | None) -> str:
    return (value or "").strip().casefold()
def find_transition_id(
    transitions: list[dict[str, Any]],
    target_status: str,
) -> str | None:
    normalized_target = normalize(target_status)
    for transition in transitions:
        destination_status = transition.get("to", {}).get("name")
        if normalize(destination_status) == normalized_target:
            transition_id = transition.get("id")
            return str(transition_id) if transition_id is not None else None
    return None
def print_available_transitions(
    transitions: list[dict[str, Any]],
) -> None:
    if not transitions:
        print("No transitions are available for this issue.")
        return
    print("Available transitions:")
    for transition in transitions:
        transition_id = transition.get("id", "unknown")
        transition_name = transition.get("name", "unknown")
        target_name = transition.get("to", {}).get("name", "unknown")
        print(
            f"  - id={transition_id}, "
            f"transition={transition_name}, "
            f"target={target_name}"
        )
def update_issue_to_qa(
    client: JiraClient,
    issue_key: str,
    target_status: str,
    qa_username: str,
) -> None:
    issue = client.get_issue(issue_key)
    fields = issue.get("fields", {})
    summary = fields.get("summary", "")
    current_status = fields.get("status", {}).get("name", "")
    current_assignee = fields.get("assignee") or {}
    current_assignee_username = (
        current_assignee.get("name")
        or current_assignee.get("key")
        or current_assignee.get("accountId")
        or ""
    )
    print(f"Issue: {issue_key}")
    print(f"Summary: {summary}")
    print(f"Current status: {current_status}")
    print(f"Current assignee: {current_assignee_username or 'Unassigned'}")
    if normalize(current_status) == normalize(target_status):
        print(
            f"{issue_key} is already in status '{target_status}'. "
            "Skipping transition."
        )
    else:
        transitions = client.get_transitions(issue_key)
        transition_id = find_transition_id(
            transitions=transitions,
            target_status=target_status,
        )
        if not transition_id:
            print_available_transitions(transitions)
            raise JiraAutomationError(
                f"No available transition from '{current_status}' "
                f"to '{target_status}' for {issue_key}."
            )
        print(
            f"Transitioning {issue_key} from "
            f"'{current_status}' to '{target_status}' "
            f"using transition ID {transition_id}."
        )
        client.transition_issue(
            issue_key=issue_key,
            transition_id=transition_id,
        )
        print(f"Transitioned {issue_key} to '{target_status}'.")
    if normalize(current_assignee_username) == normalize(qa_username):
        print(
            f"{issue_key} is already assigned to '{qa_username}'. "
            "Skipping assignment."
        )
    else:
        print(f"Assigning {issue_key} to QA user '{qa_username}'.")
        client.assign_issue(
            issue_key=issue_key,
            qa_username=qa_username,
        )
        print(f"Assigned {issue_key} to '{qa_username}'.")
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a Jira ticket from a PR or commit message, "
            "transition it to QA, and assign it to a QA user."
        )
    )
    parser.add_argument(
        "--source-text",
        required=True,
        help="PR title, workflow run name, or merge commit message.",
    )
    parser.add_argument(
        "--target-status",
        default="QA",
        help="Destination Jira status. Default: QA.",
    )
    parser.add_argument(
        "--qa-username",
        required=True,
        help="Jira username of the target QA user.",
    )
    parser.add_argument(
        "--ticket-pattern",
        default=DEFAULT_TICKET_PATTERN,
        help="Regex used to extract the Jira ticket key.",
    )
    parser.add_argument(
        "--fail-if-no-ticket",
        action="store_true",
        help="Fail instead of skipping when no Jira key is found.",
    )
    return parser.parse_args()
def main() -> int:
    args = parse_args()
    jira_base_url = os.environ.get("JIRA_BASE_URL", "").strip()
    jira_username = os.environ.get("JIRA_USERNAME", "").strip()
    jira_token = os.environ.get("JIRA_TOKEN", "").strip()
    missing_variables = [
        variable_name
        for variable_name, value in (
            ("JIRA_BASE_URL", jira_base_url),
            ("JIRA_USERNAME", jira_username),
            ("JIRA_TOKEN", jira_token),
        )
        if not value
    ]
    if missing_variables:
        raise JiraAutomationError(
            "Missing required environment variables: "
            + ", ".join(missing_variables)
        )
    issue_key = extract_jira_ticket(
        source_text=args.source_text,
        pattern=args.ticket_pattern,
    )
    if not issue_key:
        message = (
            "No Jira ticket was found in source text: "
            f"{args.source_text!r}"
        )
        if args.fail_if_no_ticket:
            raise JiraAutomationError(message)
        print(f"NOTICE: {message}")
        return 0
    print(f"Extracted Jira ticket: {issue_key}")
    verify_ssl = (
        os.environ.get("JIRA_VERIFY_SSL", "true").strip().lower()
        not in {"false", "0", "no"}
    )
    client = JiraClient(
        JiraConfig(
            base_url=jira_base_url,
            username=jira_username,
            token=jira_token,
            verify_ssl=verify_ssl,
        )
    )
    update_issue_to_qa(
        client=client,
        issue_key=issue_key,
        target_status=args.target_status,
        qa_username=args.qa_username,
    )
    return 0
if __name__ == "__main__":
    try:
        sys.exit(main())
    except JiraAutomationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except requests.RequestException as exc:
        print(f"ERROR: Jira network request failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: Jira returned invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

⸻

2. Reusable workflow

.github/workflows/transition-jira-to-qa.yml

name: Transition Jira Ticket to QA
on:
  workflow_call:
    inputs:
      source_text:
        description: PR title or merge commit message
        required: true
        type: string
      target_status:
        description: Jira target status
        required: false
        default: QA
        type: string
      qa_username:
        description: Jira username of the QA assignee
        required: true
        type: string
      ticket_pattern:
        description: Regex used to extract the Jira ticket
        required: false
        default: '\b[A-Z][A-Z0-9]+-[0-9]+\b'
        type: string
      fail_if_no_ticket:
        description: Fail when the message contains no Jira ticket
        required: false
        default: false
        type: boolean
    secrets:
      jira_base_url:
        required: true
      jira_username:
        required: true
      jira_token:
        required: true
jobs:
  update-jira:
    name: Move Jira ticket to QA
    runs-on: td-linux-runner
    steps:
      - name: Check out common workflow repository
        uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        shell: bash
        run: |
          python -m pip install --disable-pip-version-check requests
      - name: Transition and assign Jira ticket
        shell: bash
        env:
          JIRA_BASE_URL: ${{ secrets.jira_base_url }}
          JIRA_USERNAME: ${{ secrets.jira_username }}
          JIRA_TOKEN: ${{ secrets.jira_token }}
        run: |
          args=(
            --source-text "${{ inputs.source_text }}"
            --target-status "${{ inputs.target_status }}"
            --qa-username "${{ inputs.qa_username }}"
            --ticket-pattern "${{ inputs.ticket_pattern }}"
          )
          if [[ "${{ inputs.fail_if_no_ticket }}" == "true" ]]; then
            args+=(--fail-if-no-ticket)
          fi
          python scripts/transition_jira_to_qa.py "${args[@]}"

注意：你们内部 runner 可能已经有 Python 和 requests，那可以移除 setup-python 和动态安装依赖。银行内部环境下，我更推荐把依赖固定在 requirements.txt：

requests==2.32.5

再通过内部 PyPI/Nexus 安装，避免每次从公网下载。

⸻

3. Microservice caller

在原来的 merge workflow 中：

jobs:
  backend-merge:
    name: Backend merge
    uses: TD-Universe/common-workflows/.github/workflows/backend-merge.yml@v1
    secrets: inherit
  move-jira-to-qa:
    name: Move Jira ticket to QA
    needs:
      - backend-merge
    if: >-
      ${{
        always() &&
        needs.backend-merge.result == 'success' &&
        github.event.pull_request.merged == true
      }}
    uses: TD-Universe/common-workflows/.github/workflows/transition-jira-to-qa.yml@v1
    with:
      source_text: ${{ github.event.pull_request.title }}
      target_status: QA
      qa_username: qa.user
      ticket_pattern: '\bWMPTRADE-[0-9]+\b'
      fail_if_no_ticket: false
    secrets:
      jira_base_url: ${{ secrets.JIRA_BASE_URL }}
      jira_username: ${{ secrets.JIRA_USERNAME }}
      jira_token: ${{ secrets.JIRA_TOKEN }}

对于截图中的：

WMPTRADE-34173 Binary content derived from a content type (#980)

最终会提取：

WMPTRADE-34173

⸻

4. 更推荐从 PR title 读取

你截图中 GitHub Actions run name 的内容应该来自 PR title：

source_text: ${{ github.event.pull_request.title }}

这比读取 merge commit message 更稳定，因为：

* squash merge 可能改变 commit message；
* reusable workflow 中 github.event.head_commit.message 不一定存在；
* pull_request.title 对 pull_request 事件更直接；
* PR title 通常已经被团队约定为必须包含 Jira key。

还可以在 PR validation 阶段提前验证：

- name: Validate Jira ticket in PR title
  shell: bash
  env:
    PR_TITLE: ${{ github.event.pull_request.title }}
  run: |
    if ! grep -qE '\bWMPTRADE-[0-9]+\b' <<< "${PR_TITLE}"; then
      echo "::error::PR title must contain a WMPTRADE Jira ticket."
      exit 1
    fi

⸻

5. Transition 和 assignment 的顺序

我建议：

Transition to QA
→ Assign QA user

原因是 Jira workflow 可能对 transition 设置 validator 或 post-function：

* 进入 QA 时要求特定字段；
* transition 自动清理或更换 assignee；
* workflow post-function 可能覆盖你提前设置的 assignee。

因此在 transition 成功后再 assign，更不容易被覆盖。

另一种方式是把 assignee 放入 transition payload：

{
  "transition": {
    "id": "41"
  },
  "fields": {
    "assignee": {
      "name": "qa.user"
    }
  }
}

Jira Data Center 允许在 transition 时更新该 transition screen 支持的字段。

但这依赖 Jira workflow configuration。如果 assignee 不在 transition screen 或不可编辑，API 会返回 400。两个独立调用更通用、更容易排错。

⸻

6. 一个需要确认的重要细节

截图中的 Jira URL 是：

track.td.com

而 Jira issue 页面显示的是旧版用户名体系的可能性较高。你们的 assignment payload 可能是：

{"name": "qa.user"}

也可能需要：

{"key": "qa.user"}

Jira Cloud 才通常使用：

{"accountId": "..."}

因此先用 Postman 或 curl 验证：

curl \
  --user "${JIRA_USERNAME}:${JIRA_TOKEN}" \
  --header "Accept: application/json" \
  "${JIRA_BASE_URL}/rest/api/2/issue/WMPTRADE-34498?fields=assignee,status"

查看 assignee 返回的是 name、key 还是其他 identifier，再决定 assignment payload。

最终选择

不要把所有业务逻辑写进 workflow YAML 的 shell block。

推荐：

Reusable workflow：负责编排、inputs、secrets 和 runner
Python script：负责 Jira ticket 提取、状态判断、transition、assignment 和错误处理

这样以后加入以下功能时不用把 YAML 改成一大段难维护的脚本：

* 根据 component/team 分配不同 QA；
* 根据 Jira issue type 决定目标状态；
* 为 Story 和 Sub-task 使用不同 workflow；
* 添加 Jira comment；
* 批量处理 PR title 中多个 tickets；
* dry-run；
* retry；
* audit logging。