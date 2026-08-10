可以。既然你已经确认是普通 HTTPS/TLS，不是 mTLS，那整个流程其实很清楚：Config Server 证明自己的身份，App Server 只负责验证它并通过 HTTPS 拉取配置。

你可以把架构先理解成这样：

┌─────────────────────┐
│     App Server      │
│ Spring Boot App     │
│                     │
│ Trust CA / Cert     │
└──────────┬──────────┘
           │
           │ HTTPS
           │ GET /my-app/prod
           ▼
┌─────────────────────┐
│    Config Server    │
│ Spring Cloud Config │
│                     │
│ Server Certificate  │
│ Private Key         │
└─────────────────────┘

最重要的一点是：

certificate + private key 在 Config Server 这一侧。

App Server 一般没有自己的 certificate/private key，它只需要能够 trust Config Server 的 certificate。

⸻

1. 先申请 Config Server certificate

假设你的 Config Server DNS 是：

config-prod.company.com

你需要从公司内部 CA / PKI 系统申请 certificate，certificate 的 SAN 里通常要包含：

DNS: config-prod.company.com

最后一般会拿到类似：

config-server.crt
config-server.key

或者：

config-server.pem
config-server.key

有时还会给：

intermediate-ca.crt
root-ca.crt

所以概念上是：

Config Server Certificate
        +
Private Key
        +
CA Certificate Chain

其中：

* certificate 可以给别人看
* private key 只能留在 Config Server
* CA certificate 用于建立完整 trust chain

⸻

2. Config Server 上安装 certificate

这里要看 HTTPS 是在哪里 terminate 的。

这是实际环境里非常重要的一点。

情况 A：Spring Boot Config Server 自己直接提供 HTTPS

比如现在 Config Server 是：

java -jar config-server.jar

然后 Spring Boot 自己监听：

https://config-prod.company.com:8443

那么 certificate 就配置到 Spring Boot。

通常 Spring Boot 更喜欢使用 Java keystore，比如：

PKCS12

你可能先把：

config-server.crt
config-server.key

转换成：

config-server.p12

然后 Config Server：

server:
  port: 8443
  ssl:
    enabled: true
    key-store: /opt/config/certs/config-server.p12
    key-store-type: PKCS12
    key-store-password: ${KEYSTORE_PASSWORD}

这样：

Spring Boot Config Server
        │
        ├── config-server.p12
        │      ├── certificate
        │      └── private key
        │
        └── HTTPS :8443

客户端访问：

https://config-prod.company.com:8443

Spring Boot 就会把 certificate 发给客户端。

⸻

情况 B：Config Server 前面有 Load Balancer / Nginx / Apache / F5

企业环境里这个其实也非常常见。

可能真实架构是：

App Server
     │
     │ HTTPS
     ▼
┌──────────────┐
│ F5 / LB      │
│ Certificate  │
│ Private Key  │
└──────┬───────┘
       │ HTTP or HTTPS
       ▼
┌──────────────┐
│Config Server │
│ :8080        │
└──────────────┘

这种情况下，certificate 不是装在 Spring Boot Config Server 上，而是装在：

F5
Load Balancer
Reverse Proxy
Ingress

上面。

这叫：

TLS termination

所以你们团队说：

Config Certificate

未必意味着 certificate 真正在 config server OS 上。

有可能实际上是：

Config Server endpoint 的 certificate

真正安装在 F5/LB。

这个你最好确认一下你们 Config Server topology。

⸻

3. App Server 第一次连接 Config Server

假设 App Server 启动的时候配置：

spring:
  config:
    import: "configserver:https://config-prod.company.com"

或者旧版本：

spring:
  cloud:
    config:
      uri: https://config-prod.company.com

App Server 发起：

GET https://config-prod.company.com/myapp/prod

这时候 TLS handshake 先发生。

大致流程：

App Server                      Config Server
    │                                │
    │ -------- Client Hello -------> │
    │                                │
    │ <------- Server Hello -------- │
    │ <------- Certificate --------- │
    │                                │
    │  检查 certificate              │
    │                                │
    │ -------- TLS Session --------> │
    │                                │
    │ ===== Encrypted HTTPS ======== │

这里 App Server 会检查几个重要东西。

⸻

4. App Server 检查 certificate 是不是可信

假设 Config Server 发回来：

Certificate:
  Subject:
    config-prod.company.com
  Issuer:
    TD Internal CA

App Server 会检查：

Certificate 是否过期

例如：

Valid from:
2026-01-01
Valid until:
2027-01-01

Hostname 是否匹配

App Server 访问：

config-prod.company.com

certificate SAN 必须包含：

DNS:config-prod.company.com

否则可能报：

No subject alternative DNS name matching
config-prod.company.com found

CA 是否 trusted

certificate chain：

Root CA
   │
   ▼
Intermediate CA
   │
   ▼
Config Server Certificate

App Server 必须 trust：

Root CA

或者对应 intermediate CA。

⸻

5. 所以 App Server 实际上要做什么？

如果你们公司内部 CA 已经预装在 App Server/JVM truststore，那么：

App Server 可能什么 certificate 都不用安装。

直接：

https://config-prod.company.com

就可以。

比如：

App Server JVM
    │
    └── cacerts
          │
          ├── DigiCert
          ├── Entrust
          └── Company Internal Root CA

因为：

Config Server Cert
        ↓ signed by
Intermediate CA
        ↓ signed by
Company Root CA
        ↓
Already trusted by JVM

所以 Java 自动 trust。

⸻

如果公司 CA 不在 App Server truststore

那 App Server 上通常需要安装的是：

CA certificate

而不是 Config Server 的 private key。

例如：

company-root-ca.crt

导入 Java truststore：

keytool -importcert \
  -alias company-root-ca \
  -file company-root-ca.crt \
  -keystore truststore.jks

然后 JVM：

-Djavax.net.ssl.trustStore=/opt/app/certs/truststore.jks
-Djavax.net.ssl.trustStorePassword=******

关系就是：

Config Server
├── Server Certificate
└── Private Key
App Server
└── Truststore
     └── Company CA Certificate

App Server 不应该拿到 Config Server private key。

⸻

6. 最终 Spring Boot Config 拉配置

TLS 建立以后，后面才真正进入 Spring Cloud Config 流程。

例如你的应用叫：

thematic-service

Environment：

prod

它可能请求：

https://config-prod.company.com/thematic-service/prod

Config Server 查自己的 backend，例如：

Git Repository
config-repo/
├── application.yml
├── thematic-service.yml
├── thematic-service-dev.yml
├── thematic-service-pat.yml
└── thematic-service-prod.yml

然后：

Config Server
       │
       │ read Git
       ▼
thematic-service-prod.yml
       │
       ▼
return JSON/config
       │
       ▼
App Server

Spring Boot 把这些 config 加入 Environment：

datasource URL
feature flags
endpoint
timeout
etc.

然后 application 完成启动。

完整路径其实是：

1. App Server starts
          │
          ▼
2. DNS resolve config-prod.company.com
          │
          ▼
3. Connect Config Server :443
          │
          ▼
4. TLS handshake
          │
          ├── Config Server sends certificate
          │
          └── App Server verifies certificate
          │
          ▼
5. HTTPS established
          │
          ▼
6. Spring Config Client requests config
          │
          ▼
7. Config Server reads config repository
          │
          ▼
8. Config Server returns configuration
          │
          ▼
9. Spring Boot loads configuration
          │
          ▼
10. Application starts

⸻

你图里的 DEV / PAT / PROD certificate 也因此比较好理解

你截图里写：

Config Certificate
  DEV  (Not needed as we use shared one)
  PAT  (Pending)
  PROD/DRP (Pending)

我会倾向于理解成类似：

DEV
config-dev.shared.company.com
      │
      └── 已有共享 certificate
           所以不用重新申请
PAT
config-pat.company.com
      │
      └── 需要 certificate
PROD
config-prod.company.com
      │
      └── 需要 certificate

这跟截图里的描述非常吻合。

所以这里的 Config Certificate 不是给每个 App Server 发一个身份证。

而是：

Config Server HTTPS endpoint 的身份证。

比如有 10 个 App Server：

App A ─┐
App B ─┤
App C ─┤
App D ─┼── HTTPS ──> config-prod.company.com
App E ─┤                   │
App F ─┤                   └── 一个 server certificate
App G ─┤
App H ─┘

这 8 个 application 完全可以访问同一个 Config Server certificate。

⸻

还有一个你之后很可能会碰到的问题：certificate 并不等于 authorization。普通 TLS 只解决“这个 Config Server 是真的 + 通信加密”；如果需要限制“App A 只能读 A 的 config、App B 只能读 B 的 config”，还要另外通过 Basic Auth、token、OAuth/service account 或其他机制做认证授权，而不是靠这里这个 server certificate。