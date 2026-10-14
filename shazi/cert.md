两个目录的文件**大小和时间戳完全一致**（cacerts 195731、webbroker.delta.td.com.jks 17229，都是 2025-07-21 15:19），所以昨天的 deploy 没有改动证书内容 —— 只是动了目录本身。先一条命令钉死这个结论：

```bash
sudo sha256sum /app/webAS/config/ssl/* /app/webAS/config/ssl-bkp/*
```

指纹一样 → **证书不是变量，不用比了，也不用回滚**。问题在别处。

## 那最可能是什么

证书是 2025-07-21 的。如果签的是 1 年期，**现在已经过期了**。这是当前第一嫌疑：

```bash
keytool -list -v -keystore /app/webAS/config/ssl/webbroker.delta.td.com.jks \
  -storepass <pwd> | grep -E "Alias name|Entry type|Owner|Issuer|Valid from|Serial number"
```

盯 `Valid from ... until ...`。过期的话服务端拒绝时发 `certificate_unknown` 是常见行为（不是所有实现都发 certificate_expired）。

顺带看 truststore 里 CA 的有效期：
```bash
keytool -list -v -keystore /app/webAS/config/ssl/cacerts -storepass changeit \
  | grep -E "Alias name|Valid from" | head -40
```

## 你刚敲的 openssl 命令有两处错

```
openssl s_client -connect http://webbroker.config.dev.td.com:19988 -cert .../webbroker.delta.td.com.jks
```

- `-connect` 不能带 `http://`，只要 `host:port`
- `-cert` 收的是 PEM，**不能直接喂 .jks**

jks 要先转出来：
```bash
cd /tmp
keytool -importkeystore -srckeystore /app/webAS/config/ssl/webbroker.delta.td.com.jks \
  -srcstorepass <pwd> -destkeystore /tmp/client.p12 -deststoretype PKCS12 -deststorepass changeit

openssl pkcs12 -in /tmp/client.p12 -passin pass:changeit -clcerts -nokeys -out /tmp/client.crt
openssl pkcs12 -in /tmp/client.p12 -passin pass:changeit -nocerts -nodes -out /tmp/client.key

openssl x509 -in /tmp/client.crt -noout -subject -issuer -dates -serial

openssl s_client -connect webbroker.config.dev.td.com:19988 \
  -servername webbroker.config.dev.td.com \
  -cert /tmp/client.crt -key /tmp/client.key </dev/null 2>&1 | tail -30
```

用完删掉 `/tmp/client.*`，里面有私钥。

## 如果证书没过期

那就是**服务端侧变了** —— config server 换了信任的 CA、或者加了新的校验规则。这种情况你这边改不了，要找管 webbroker.config.dev.td.com 的团队确认他们最近有没有动 TLS 配置。

顺便查一下服务端证书有没有换：
```bash
openssl s_client -connect webbroker.config.dev.td.com:19988 </dev/null 2>&1 \
  | openssl x509 -noout -subject -issuer -dates
```
对方证书的 Issuer 如果不在你的 cacerts 里，也要一并处理。

把 `keytool -list -v` 的 Valid from/until 发我，基本就能定性了。
