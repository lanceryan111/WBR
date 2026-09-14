图里的文件现在是**两种格式混在一起**：上半段是旧的扁平格式（`ENV_VARS` / `JVM_ARGS` 在顶层），下半段是新的按 app 嵌套格式。上半段会被 `package_app_config` 直接拒掉（"found at the top level"），而且里面的路径是 `webbroker-notification`，看着像从别的 service 复制来的。

我按嵌套格式给你生成一套完整的 fraud-detection dev 模板，四个 app 都有，用真实的 validator 验过。`dev-config.yml` 直接贴一份，方便对照：

```yaml
# wbr_wbrsvc-fraud-detection / dev-config.yml
#
# 规则（package_app_config 会校验）：
#   - 顶层 key = app 名，必须跟 ansible group_vars/all.yml 里 applications[].name
#     完全一致，区分大小写：Fraudster / Solacer / Cleaner / Mailer
#   - 每个 app 下面只认三个 key：JVM_ARGS(list) / RUN_ARGS(list) / ENV_VARS(map)
#   - 这里写的会 deep-merge 到 defaults.yml 上面：同 key 以这里为准，
#     defaults 有、这里没有的 key 原样保留
#   - 没写的 app 走 group_vars / start_app.sh.j2 的默认值
#
# start_app.sh.j2 已经固定带了这几个 flag，JVM_ARGS 里不要再写，写了也会被
# 模板后面那份盖掉（同名 -D 以最后一个为准）：
#   -XX:+CrashOnOutOfMemoryError  -XX:+HeapDumpOnOutOfMemoryError
#   -XX:HeapDumpPath=${LOG_LOCATION}
#   -Dspring.config.additional-location=${CONFIG_DIRECTORY}/bootstrap.properties
#   -Dlogging.file.path=${LOG_LOCATION}
# 其中 CONFIG_DIRECTORY = /app/webAS/config/<AppName>，LOG_LOCATION = /app/logs/<AppName>

Fraudster:
  JVM_ARGS:
    - "-Xms512m"
    - "-Xmx1024m"
    - "-Dobjectgrid.client.props=/app/webAS/config/Fraudster/client.properties"
    - "-Dfraudster.rules.refresh.seconds=30"
  ENV_VARS:
    SPRING_PROFILES_ACTIVE: dev
    LOG_PATH: /app/logs/Fraudster
  # RUN_ARGS 是 jar 后面的程序参数，不是 JVM 参数。大多数 app 用不到，留空或注释掉
  # RUN_ARGS:
  #   - "--server.port=8443"

Solacer:
  JVM_ARGS:
    - "-Xms256m"
    - "-Xmx512m"
    - "-Dsolace.client.props=/app/webAS/config/Solacer/solace.properties"
  ENV_VARS:
    SPRING_PROFILES_ACTIVE: dev

Cleaner:
  JVM_ARGS:
    - "-Xms256m"
    - "-Xmx512m"
  ENV_VARS:
    SPRING_PROFILES_ACTIVE: dev
    CLEANER_DRY_RUN: "true"

Mailer:
  JVM_ARGS:
    - "-Xms256m"
    - "-Xmx512m"
  ENV_VARS:
    SPRING_PROFILES_ACTIVE: dev
    MAIL_SINK: /app/logs/Mailer/outbox
```

里面的 `-D` 值和 ENV_VARS 名字是我编的占位，换成你们真实的。

三个要注意的：

**你截图里那个文件必须把上半段删掉。** 顶层的 `ENV_VARS:` / `JVM_ARGS:` / `#RUN_ARGS:` 那块是旧的扁平格式，validator 会报 `ENV_VARS, JVM_ARGS found at the top level` 然后整个 service 打包失败。只留下面按 app 嵌套的部分。另外那段里的 `webbroker-notification` / `wbr-service-notification` 路径不属于 fraud-detection。

**list 是整体替换，不是追加。** `combine(recursive=True)` 对 dict 是按 key 合并，对 list 是直接覆盖。所以 `ENV_VARS` 会合并（defaults 的 `TZ` + dev 的 `SPRING_PROFILES_ACTIVE` 都在），但 `JVM_ARGS` 是 dev 的整个列表替换 defaults 的整个列表 —— dev 里的 `JVM_ARGS` 得写全，不能只写"比 defaults 多出来的那几个"。上面验证输出第 2 段就是这个效果。

**别在 JVM_ARGS 里重复模板已经带的 flag。** 你截图里有一条 `-Dspring.config.additional-location=file:...`，但模板的 `JAVA_OPTS` 已经固定带了 `-Dspring.config.additional-location=${CONFIG_DIRECTORY}/bootstrap.properties`，而且排在配置值**后面** —— JVM 同名 `-D` 以最后一个为准，所以配置里那条会被静默盖掉，看起来像没生效。真要按环境改这个路径，就把模板里那条删掉，让配置来定。