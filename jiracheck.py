加上 `not_found_keys` 缓存。现在存在和不存在两种结果都会被记住,同一个 key 在整个 PR 里最多只查一次 API。

```python
import os
import re
import logging
import requests
from datetime import datetime
from wbr_util import gh_rest_api


def validate_jira_in_commit():
    project_name = os.environ.get("PROJECT_NAME")
    project_ref_name = os.environ.get("PROJECT_REF_NAME")
    gh_token = os.environ.get("GH_TOKEN")
    project_ref_list = project_ref_name.split("/")
    if len(project_ref_list) != 2:
        # for merge queue, the ref name is in the format like "gh-readonly-queue/develop/pr-116-acb787..."
        pr_id = project_ref_list[-1].split("-")[1]
    else:
        pr_id = project_ref_list[0]
    logging.info(f"project name is {project_name}")
    logging.info(f"gh ref name is {project_ref_name}")
    logging.info(f"pr id is {pr_id}")
    pr_info = gh_rest_api.get_pull_request_info(gh_token, project_name, pr_id)
    logging.info(f"pr info is {pr_info}")
    has_valid_jira_commit = False
    verified_keys = set()
    not_found_keys = set()
    for commit in pr_info:
        commit_message = commit["commit"]["message"]
        logging.info(f"commit message is {commit_message}")
        if not check_merge_into_branch_commit(commit_message) and not check_onboarding_commit(commit_message):
            # check if message contain jira number
            jira_pattern = r"(WMPTRADE-\d{1,6}|TDWARTSE-\d{1,6}|WBR-\d{1,6}|TDWDIET-\d{1,6}|WB-\d{1,6})"
            match = re.search(jira_pattern, commit_message)

            if match:
                issue_key = match.group(0)
                logging.info(f"JIRA key pattern matched in commit message: {issue_key}")
                if issue_key in not_found_keys:
                    logging.info(f"JIRA key {issue_key} already known not to exist, skip")
                    continue
                if issue_key in verified_keys or jira_ticket_exists(issue_key):
                    logging.info(f"JIRA ticket {issue_key} verified as existing")
                    verified_keys.add(issue_key)
                    has_valid_jira_commit = True
                    break
                else:
                    logging.info(f"JIRA key {issue_key} matched format but ticket not found, continue checking")
                    not_found_keys.add(issue_key)

    if not has_valid_jira_commit:
        raise Exception(f"No valid Jira number found in the commit history")


def jira_ticket_exists(issue_key):
    jira_base_url = os.environ.get("JIRA_BASE_URL")
    jira_token = os.environ.get("JIRA_TOKEN")
    url = f"{jira_base_url}/rest/api/2/issue/{issue_key}"
    headers = {
        "Authorization": f"Bearer {jira_token}",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException as e:
        logging.error(f"JIRA API request failed for {issue_key}: {e}")
        # fail-open: JIRA 不可达时不阻塞,退回到只信任 regex 格式匹配
        return True
    if resp.status_code == 200:
        return True
    if resp.status_code == 404:
        logging.warning(f"JIRA ticket {issue_key} does not exist (404)")
        return False
    logging.error(f"Unexpected JIRA response {resp.status_code} for {issue_key}")
    # 非 404 的异常状态,同样 fail-open,避免 JIRA 抖动误伤
    return True


def check_merge_into_branch_commit(commit_message):
    pattern = r"^Merge.* branch .* into .*"
    match = re.search(pattern, commit_message)
    logging.info(f"check merge into branch result is {match}")
    return bool(match)


def check_onboarding_commit(commit_message):
    pattern = r"^Onboarding: SonarQube configuration files"
    match = re.search(pattern, commit_message)
    logging.info(f"check onboarding commit result is {match}")
    return bool(match)
```

循环里现在的判断顺序:先查 `not_found_keys`,命中就直接 `continue` 跳过这个 commit(既不重复调 API 也不重复打"not found"日志);否则查 `verified_keys` 或调 API,存在则记入 `verified_keys` 并 break,不存在则记入 `not_found_keys` 继续。

有个边界情况值得留意:fail-open 分支会让不可达/5xx 的 key 返回 True 并进 `verified_keys`。这意味着 JIRA 临时抖动期间,一个本可能不存在的 key 会被当成有效直接放行。这是 fail-open 的固有取舍,不是缓存引入的问题。如果哪天想把不可达和"确认存在"区分开(比如不可达的结果不缓存,以便后续 commit 有机会重试),可以让 `jira_ticket_exists` 返回三态而不是布尔。现在这版对正常场景够用,先不过度设计。