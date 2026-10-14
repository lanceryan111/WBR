关键在于：`certificate_unknown` 这行是 **INFO 级别**，每次启动都会写进应用日志。所以**日志里第一次出现它的时间点，就是问题开始的时间** —— 跟 systemd 的 active 状态完全无关。

## 1. 直接定位首次出现

```bash
cd /app/logs/WebLogs/wbr_thematic_invest_dev/

# 按时间排序列出所有日志文件（含归档）
ls -la --time-style=long-iso

# 每个文件里第一条 certificate_unknown 的时间戳
for f in $(ls -tr *.log* 2>/dev/null); do
  t=$(zgrep -m1 -o '"@timestamp":"[^"]*"' "$f" 2>/dev/null | head -1)
  c=$(zgrep -c certificate_unknown "$f" 2>/dev/null)
  echo "$f | first_ts=$t | cert_unknown=$c"
done
```

`cert_unknown` 从 0 变成非 0 的那个文件，边界就在里面。注意用 `zgrep`，归档日志通常是 .gz。

## 2. 列出每次启动的成败历史

这是最有价值的一张表 —— 每次启动到底拉到配置没有：

```bash
zgrep -h -o '"@timestamp":"[^"]*".*\(Located environment\|Could not locate PropertySource\|certificate_unknown\)' *.log* \
  | sed 's/.*"@timestamp":"\([^"]*\)".*\(Located environment\|Could not locate PropertySource\|certificate_unknown\).*/\1 \2/' \
  | sort | uniq
```

或者更稳妥地分开看：
```bash
# 历次成功拉配置的时间
zgrep -h "Located environment" *.log* | grep -o '"@timestamp":"[^"]*"' | sort | uniq

# 历次失败的时间
zgrep -h "certificate_unknown" *.log* | grep -o '"@timestamp":"[^"]*"' | cut -c1-27 | sort -u | head -40
```

**最后一次 `Located environment` 的时间 = 最后一次正常工作的时间。** 这个数字直接回答 Matthew 的"上周还好用"。

## 3. 对照 systemd 的重启历史

```bash
journalctl -u webbroker-wbr-thematic-invest_dev --since "2026-09-01" \
  | grep -iE "Started|Stopped|Main process" 
```

把这个时间轴和上面的失败时间轴叠在一起看，就能确定：
- 9 月、10 月初重启过且 `Located environment` 成功 → 你的 deploy 前还是好的，问题确实在昨天之后
- 4 月之后压根没重启过 → "上周好用"只是进程没重启，问题早就存在

注意 journalctl 可能有保留期限制，查一下范围：
```bash
journalctl --disk-usage
journalctl -u webbroker-wbr-thematic-invest_dev --since "2026-01-01" | head -5
```

## 4. 顺带确认进程实际运行了多久

```bash
ps -o lstart= -p 468450
systemctl show webbroker-wbr-thematic-invest_dev -p ActiveEnterTimestamp
```

进程启动时间如果远早于今天，说明它一直带着老配置在跑。

## 5. 为什么 active 骗人

补一句根因，便于你后面改进：`fail-fast` 没开。确认一下：

```bash
grep -i "fail-fast\|failFast" /app/webAS/config/wbr-thematic-invest/dev/bootstrap.properties
```

没配或是 false 的话，config server 拉不到配置应用照样启动，systemd 当然显示 active。建议后续加上 `spring.cloud.config.fail-fast=true`，以及给 systemd 加 healthcheck，这类问题就不会再潜伏半年。

第 2 步那个"最后一次 Located environment"的时间最关键，拿到了发我。