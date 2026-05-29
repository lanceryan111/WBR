curl -s -w "\nHTTP_CODE:%{http_code}\n" \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Accept: application/json" \
  "https://<jira-base>/rest/scriptrunner/latest/custom/jigitWrapper/<hardcoded-repo-id>"
