可以直接沿用你们现有脚本的风格：

* 从 environment variables 读取 JIRA_BASE_URL、JIRA_TOKEN
* 使用 Bearer token
* 使用 /rest/api/2
* 使用 logging
* 不包含 main()
* 对外提供一个主要 function，供另一个脚本 import 后调用
* 先检查 ticket、读取状态、查找 QA transition、执行 transition，最后 assign QA

建议新建：

wbr_actions/transition_jira_ticket.py
import logging
import os
import re
import requests
DEFAULT_JIRA_PATTERN = (
    r"\b(?:WMPTRADE|TDWARTSE|WBR|TDWDIET|WB)-\d{1,6}\b"
)
def transition_jira_ticket_to_qa(
    commit_message,
    qa_username,
    target_status="QA",
    jira_pattern=DEFAULT_JIRA_PATTERN,
):
    """
    Extract a JIRA ticket from the commit message, transition it to QA,
    and assign it to the specified QA user.
    Args:
        commit_message: Pull request commit message or PR title.
        qa_username: JIRA username of the QA assignee.
        target_status: Target JIRA status. Default is QA.
        jira_pattern: Regex used to extract the JIRA ticket.
    Returns:
        str: Extracted JIRA ticket number.
    Raises:
        Exception: When ticket extraction, validation, transition,
                   or assignment fails.
    """
    logging.info(f"Commit message is: {commit_message}")
    jira_ticket = extract_jira_ticket(
        commit_message=commit_message,
        jira_pattern=jira_pattern,
    )
    logging.info(
        f"JIRA ticket number matched in commit message: {jira_ticket}"
    )
    issue = get_jira_issue(jira_ticket)
    current_status = (
        issue.get("fields", {})
        .get("status", {})
        .get("name", "")
    )
    current_assignee = (
        issue.get("fields", {})
        .get("assignee") or {}
    )
    current_assignee_name = (
        current_assignee.get("name")
        or current_assignee.get("key")
        or ""
    )
    logging.info(
        f"JIRA ticket {jira_ticket} current status: "
        f"{current_status or 'Unknown'}"
    )
    logging.info(
        f"JIRA ticket {jira_ticket} current assignee: "
        f"{current_assignee_name or 'Unassigned'}"
    )
    if normalize_value(current_status) == normalize_value(target_status):
        logging.info(
            f"JIRA ticket {jira_ticket} is already in "
            f"{target_status}. Skipping transition."
        )
    else:
        transition_id = get_transition_id(
            jira_ticket=jira_ticket,
            target_status=target_status,
        )
        transition_jira_ticket(
            jira_ticket=jira_ticket,
            transition_id=transition_id,
            target_status=target_status,
        )
    if normalize_value(current_assignee_name) == normalize_value(qa_username):
        logging.info(
            f"JIRA ticket {jira_ticket} is already assigned to "
            f"{qa_username}. Skipping assignment."
        )
    else:
        assign_jira_ticket(
            jira_ticket=jira_ticket,
            qa_username=qa_username,
        )
    logging.info(
        f"JIRA ticket {jira_ticket} was successfully moved to "
        f"{target_status} and assigned to {qa_username}"
    )
    return jira_ticket
def extract_jira_ticket(
    commit_message,
    jira_pattern=DEFAULT_JIRA_PATTERN,
):
    """
    Extract the first valid JIRA ticket number from a commit message.
    """
    if not commit_message:
        raise Exception("Commit message is empty")
    match = re.search(
        jira_pattern,
        commit_message,
        flags=re.IGNORECASE,
    )
    if not match:
        raise Exception(
            "No valid JIRA ticket number found in the commit message"
        )
    return match.group(0).upper()
def get_jira_issue(jira_ticket):
    """
    Fetch a JIRA ticket and confirm that it exists.
    """
    jira_base_url, headers = get_jira_api_config()
    url = (
        f"{jira_base_url}/rest/api/2/issue/{jira_ticket}"
        "?fields=status,assignee,summary"
    )
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10,
        )
    except requests.RequestException as error:
        logging.error(
            f"JIRA API request failed for {jira_ticket}: {error}"
        )
        raise Exception(
            f"Unable to retrieve JIRA ticket {jira_ticket}"
        ) from error
    logging.info(
        f"JIRA API responded for {jira_ticket} with "
        f"status {response.status_code}"
    )
    if response.status_code == 200:
        logging.info(
            f"JIRA API confirmed ticket {jira_ticket} exists"
        )
        return response.json()
    if response.status_code == 404:
        raise Exception(
            f"JIRA ticket {jira_ticket} does not exist"
        )
    if response.status_code in (401, 403):
        raise Exception(
            f"JIRA API authentication or authorization failed "
            f"with status {response.status_code}"
        )
    raise Exception(
        f"Unexpected JIRA response {response.status_code} "
        f"while retrieving {jira_ticket}: "
        f"{get_response_text(response)}"
    )
def get_transition_id(jira_ticket, target_status):
    """
    Get the transition ID that moves the issue to the target status.
    Transition IDs should not be hardcoded because they may differ based
    on the ticket's current workflow and status.
    """
    jira_base_url, headers = get_jira_api_config()
    url = (
        f"{jira_base_url}/rest/api/2/issue/"
        f"{jira_ticket}/transitions"
    )
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=10,
        )
    except requests.RequestException as error:
        logging.error(
            f"Failed to retrieve transitions for "
            f"{jira_ticket}: {error}"
        )
        raise Exception(
            f"Unable to retrieve transitions for {jira_ticket}"
        ) from error
    if response.status_code != 200:
        raise Exception(
            f"Failed to retrieve transitions for {jira_ticket}. "
            f"Status: {response.status_code}, "
            f"response: {get_response_text(response)}"
        )
    transitions = response.json().get("transitions", [])
    logging.info(
        f"Available transitions for {jira_ticket}: "
        f"{format_transitions(transitions)}"
    )
    for transition in transitions:
        destination_status = (
            transition.get("to", {}).get("name", "")
        )
        if normalize_value(destination_status) == normalize_value(
            target_status
        ):
            transition_id = str(transition.get("id"))
            logging.info(
                f"Matched transition ID {transition_id} "
                f"for target status {target_status}"
            )
            return transition_id
    raise Exception(
        f"No available transition to status {target_status} "
        f"for JIRA ticket {jira_ticket}. Available transitions: "
        f"{format_transitions(transitions)}"
    )
def transition_jira_ticket(
    jira_ticket,
    transition_id,
    target_status,
):
    """
    Execute the JIRA workflow transition.
    """
    jira_base_url, headers = get_jira_api_config()
    url = (
        f"{jira_base_url}/rest/api/2/issue/"
        f"{jira_ticket}/transitions"
    )
    payload = {
        "transition": {
            "id": transition_id,
        }
    }
    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=10,
        )
    except requests.RequestException as error:
        logging.error(
            f"Failed to transition JIRA ticket "
            f"{jira_ticket}: {error}"
        )
        raise Exception(
            f"Unable to transition JIRA ticket {jira_ticket}"
        ) from error
    # Jira normally returns HTTP 204 after a successful transition.
    if response.status_code not in (200, 204):
        raise Exception(
            f"Failed to transition JIRA ticket {jira_ticket} "
            f"to {target_status}. "
            f"Status: {response.status_code}, "
            f"response: {get_response_text(response)}"
        )
    logging.info(
        f"JIRA ticket {jira_ticket} transitioned successfully "
        f"to {target_status}"
    )
def assign_jira_ticket(jira_ticket, qa_username):
    """
    Assign the JIRA ticket to the specified QA user.
    This uses the Jira Server/Data Center username field.
    """
    if not qa_username:
        raise Exception("QA username is empty")
    jira_base_url, headers = get_jira_api_config()
    url = (
        f"{jira_base_url}/rest/api/2/issue/"
        f"{jira_ticket}/assignee"
    )
    payload = {
        "name": qa_username,
    }
    try:
        response = requests.put(
            url,
            headers=headers,
            json=payload,
            timeout=10,
        )
    except requests.RequestException as error:
        logging.error(
            f"Failed to assign JIRA ticket "
            f"{jira_ticket}: {error}"
        )
        raise Exception(
            f"Unable to assign JIRA ticket {jira_ticket}"
        ) from error
    # Jira normally returns HTTP 204 after successful assignment.
    if response.status_code not in (200, 204):
        raise Exception(
            f"Failed to assign JIRA ticket {jira_ticket} "
            f"to {qa_username}. "
            f"Status: {response.status_code}, "
            f"response: {get_response_text(response)}"
        )
    logging.info(
        f"JIRA ticket {jira_ticket} assigned successfully "
        f"to {qa_username}"
    )
def get_jira_api_config():
    """
    Read and validate the JIRA REST API configuration.
    """
    jira_base_url = os.environ.get("JIRA_BASE_URL")
    jira_token = os.environ.get("JIRA_TOKEN")
    if not jira_base_url:
        raise Exception(
            "Required environment variable JIRA_BASE_URL is missing"
        )
    if not jira_token:
        raise Exception(
            "Required environment variable JIRA_TOKEN is missing"
        )
    headers = {
        "Authorization": f"Bearer {jira_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    return jira_base_url.rstrip("/"), headers
def normalize_value(value):
    """
    Normalize text values for case-insensitive comparison.
    """
    return str(value or "").strip().casefold()
def format_transitions(transitions):
    """
    Format available transitions for logs and error messages.
    """
    if not transitions:
        return "None"
    formatted_transitions = []
    for transition in transitions:
        transition_id = transition.get("id", "Unknown")
        transition_name = transition.get("name", "Unknown")
        destination_status = (
            transition.get("to", {}).get("name", "Unknown")
        )
        formatted_transitions.append(
            f"{transition_name} -> {destination_status} "
            f"(id={transition_id})"
        )
    return ", ".join(formatted_transitions)
def get_response_text(response):
    """
    Return a bounded response body for logging.
    """
    return response.text[:1000] if response.text else "Empty response"

调用这个脚本的方式

另外一个 Python 脚本里：

import logging
from wbr_actions.transition_jira_ticket import (
    transition_jira_ticket_to_qa,
)
def run_jira_transition():
    commit_message = (
        "WMPTRADE-34173 Binary content derived "
        "from a content type (#980)"
    )
    jira_ticket = transition_jira_ticket_to_qa(
        commit_message=commit_message,
        qa_username="qa.username",
        target_status="QA",
    )
    logging.info(
        f"Completed JIRA transition for ticket {jira_ticket}"
    )

假如调用脚本已经从 GitHub API 获取到了最后一个 commit message，可以直接接你现在的代码：

commit_message = pr_info[-1]["commit"]["message"]
transition_jira_ticket_to_qa(
    commit_message=commit_message,
    qa_username=os.environ.get("QA_USERNAME"),
)

GitHub Actions step

- name: Transition JIRA ticket to QA
  env:
    PROJECT_NAME: ${{ github.repository }}
    PROJECT_REF_NAME: ${{ github.ref_name }}
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    JIRA_BASE_URL: ${{ secrets.JIRA_BASE_URL }}
    JIRA_TOKEN: ${{ secrets.JIRA_TOKEN }}
    QA_USERNAME: ${{ inputs.qa_username }}
  run: |
    python path/to/caller_script.py

和你现有 validation 脚本不同的地方

你现在的 jira_ticket_exists() 对这些情况是 fail-open：

requests exception
401
403
unexpected response

都会返回 True，这是合理的，因为它只是 PR validation，不希望 Jira 临时不可用阻塞 PR。

但 transition ticket 是写操作，建议采用 fail-closed：

JIRA API error
→ GitHub Actions job fails
→ 不假装 ticket 已经成功进入 QA

否则可能出现 workflow 显示成功，但 ticket 实际还停留在 In Progress。

另外，目前代码用：

payload = {
    "name": qa_username,
}

这与截图中 Jira Server/Data Center 的 /rest/api/2 比较匹配。假如 assign API 返回 400，检查 Jira 返回的 assignee 对象到底使用 name 还是 key，再把 payload 改成：

payload = {
    "key": qa_username,
}