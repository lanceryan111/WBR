服务名是 `webbroker-wbr-thematic-invest_dev.service`。`twbrsrvid` 没有 sudo,先 `exit` 回 tae7052:

```bash
exit

# 重启前先确认当前状态
sudo systemctl status webbroker-wbr-thematic-invest_dev

# 重启
sudo systemctl restart webbroker-wbr-thematic-invest_dev

# 看是否起来
sudo systemctl status webbroker-wbr-thematic-invest_dev
```

然后跟日志确认证书加载没报错:

```bash
sudo tail -f /app/logs/WebLogs/wbr_thematic_invest_dev/ThematicService*.log
```

**重启前建议先确认两件事:**

1. **配置里引用的文件名对不对** —— 你把 `.txt` 改成了 `.pem`,确认 bootstrap.properties 里写的就是 `.pem`:
   ```bash
   sudo grep -i "pem\|ssl\|keystore\|certificate" /app/webAS/config/wbr-thematic-invest/dev/bootstrap.properties
   ```

2. **服务跑在哪个用户下** —— 文件现在是 `root:unix_svc_wbr_service 750`,只有 root 和组内成员能读:
   ```bash
   sudo systemctl show webbroker-wbr-thematic-invest_dev -p User -p Group
   id twbrsrvid   # 确认在 unix_svc_wbr_service 组里
   ```
   如果服务以 `twbrsrvid` 跑而它不在那个组,就会读不到证书启动失败。

万一起不来,回滚很快:把 `wtinv-api.dev.td.com.crt.pem.PREVIOUS` 复制回 `.pem` 再重启。