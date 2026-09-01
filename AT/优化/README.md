按优先级给你可直接粘贴的改动。

## P0-1 · upload-artifact 加 `overwrite`(6 处)

**Android**

```yaml
- name: Archive Test Reports
  if: ${{ !cancelled() }}
  uses: actions/upload-artifact@v4
  with:
    name: android_test_reports
    path: |
      # ...（保持原样）
    if-no-files-found: ignore
    retention-days: 1
    overwrite: true
```

```yaml
- name: Upload unsigned APKs
  uses: actions/upload-artifact@v4
  with:
    name: unsigned-apks
    path: unsigned-apks/
    if-no-files-found: error
    retention-days: 1
    overwrite: true
```

```yaml
- name: Upload signed APK
  uses: actions/upload-artifact@v4
  with:
    name: signed-${{ matrix.artifact }}
    path: ${{ github.workspace }}/signed-apks/${{ matrix.artifact }}.apk
    if-no-files-found: error
    retention-days: 1
    overwrite: true
```

**iOS**

```yaml
- name: Export Test Artifacts
  uses: actions/upload-artifact@v4
  with:
    name: tests_reports_UnitTestPlan
    path: build/reports/coverage/
    if-no-files-found: error
    overwrite: true
```

```yaml
- name: Upload Unsigned IPA
  uses: actions/upload-artifact@v4
  with:
    name: TDWealth_unsigned_${{ matrix.configuration }}-${{ matrix.platform }}
    path: ${{ github.workspace }}/${{ steps.locate-ipa.outputs.ipa_path }}
    if-no-files-found: error
    overwrite: true
```

```yaml
- name: Upload Resigned IPA
  uses: actions/upload-artifact@v4
  with:
    name: TDWealth_${{ matrix.configuration }}-${{ matrix.platform }}.ipa
    path: ${{ github.workspace }}/TDWealth_${{ matrix.configuration }}-${{ matrix.platform }}.ipa
    if-no-files-found: error
    overwrite: true
```

## P0-2 · Confluence 重复页面护栏(Android publish)

把原来的 `Publish Android` 一步拆成两步:

```yaml
- name: Publish Android
  env:
    tdNexusUsername: ${{ secrets.NEXUS_ID }}
    tdNexusPassword: ${{ secrets.NEXUS_PASS }}
    BUILD_NUMBER: ${{ github.run_number }}.${{ github.run_attempt }}
    GIT_COMMIT: ${{ github.sha }}
    GIT_PREVIOUS_SUCCESSFUL_COMMIT: ${{ needs.build.outputs.baseline_commit }}
    GIT_BRANCH: ${{ github.ref_name }}
    BUILD_URL: ${{ github.event.repository.html_url }}/actions/runs/${{ github.run_id }}
    ARTIFACT_SUFFIX: ${{ needs.build.outputs.artifact_suffix }}
    ADDITIONAL_PARAMS: ${{ needs.build.outputs.additional_params }}
  run: |
    set -euo pipefail
    ./gradlew -PtdBuild=true \
      -Ptd.artifactIdSuffix="$ARTIFACT_SUFFIX" \
      -Ptd.skipPublicationBuild=true \
      $ADDITIONAL_PARAMS --info --stacktrace \
      :app:publish
  shell: bash

- name: Publish Release Notes
  # 护栏:仅第一次 attempt 发 Confluence 页面,重跑不再产生重复页
  # 待 gradle 侧把 publishReleaseNotes 改成 upsert(按标题查→PUT version+1)后删除此条件
  if: github.run_attempt == '1'
  env:
    USERNAME: ${{ secrets.CONFLUENCE_ID }}
    PASSWORD: ${{ secrets.CONFLUENCE_PASS }}
    BUILD_NUMBER: ${{ github.run_number }}.${{ github.run_attempt }}
    GIT_COMMIT: ${{ github.sha }}
    GIT_PREVIOUS_SUCCESSFUL_COMMIT: ${{ needs.build.outputs.baseline_commit }}
    GIT_BRANCH: ${{ github.ref_name }}
    BUILD_URL: ${{ github.event.repository.html_url }}/actions/runs/${{ github.run_id }}
    ADDITIONAL_PARAMS: ${{ needs.build.outputs.additional_params }}
  run: |
    set -euo pipefail
    ./gradlew -PtdBuild=true \
      -Ptd.skipPublicationBuild=true \
      $ADDITIONAL_PARAMS --info --stacktrace \
      :app:publishReleaseNotes
  shell: bash
```

同时 `Share Android Confluence Link` 也要跟着跳过,否则重跑必失败:

```yaml
- name: Share Android Confluence Link
  if: github.run_attempt == '1'
  run: |
    # ...（内容不变）
```

## P0-3 · iOS unzip 加 `-o`

```yaml
- name: Unzip Dependencies
  run: |
    set -euo pipefail

    unzip_into() {
      local zip="$1" dest="$2"
      [[ -f "$zip" ]] || { echo "::error::Missing archive: $zip"; exit 1; }
      mkdir -p "$dest"
      unzip -oq "$zip" -d "$dest"
    }

    unzip_into dxmobile.zip dxmobile/
    unzip_into TDWealth/JRE.xcframework/ios-arm64/JRE.framework/JRE.zip \
               TDWealth/JRE.xcframework/ios-arm64/JRE.framework/
    unzip_into TDWealth/JRE.xcframework/ios-arm64_x86_64-simulator.zip \
               TDWealth/JRE.xcframework/ios-arm64_x86_64-simulator/
  shell: bash
```

## P1-1 · Nexus 版本号带 attempt(已含在 P0-2 里)

```yaml
BUILD_NUMBER: ${{ github.run_number }}.${{ github.run_attempt }}
```

iOS 侧对应:

```yaml
VERSION_NUMBER: ${{ github.run_number }}.${{ github.run_attempt }}
BUILD_NUMBER: ${{ github.run_number }}.${{ github.run_attempt }}
```

> 先确认 gradle 里 `BUILD_NUMBER` 参与的版本号格式接受 `.`;若只允许整数,改用 `${{ github.run_number }}` + 单独传 `RUN_ATTEMPT`。

## P1-2 · sign job 显式清理 + 签名后断言(Android)

替换原来的 `Prepare signed APK directory`,注意**排在 Download 之前**:

```yaml
steps:
  - name: Prepare workspace
    # 本 job 无 checkout,workspace 不受 git clean 保护,必须显式清理
    run: |
      set -euo pipefail
      rm -rf "${{ github.workspace }}/unsigned-apks" "${{ github.workspace }}/signed-apks"
      mkdir -p "${{ github.workspace }}/signed-apks"
    shell: bash

  - name: Download unsigned APKs
    uses: actions/download-artifact@v4
    with:
      name: unsigned-apks
      path: ${{ github.workspace }}/unsigned-apks

  - name: Sign APK
    uses: TD-Universe/common-actions/signing-service@v1
    with:
      platform: android
      artifact_path: ${{ github.workspace }}/unsigned-apks/${{ matrix.artifact }}.apk
      output_path: ${{ github.workspace }}/signed-apks/${{ matrix.artifact }}.apk
      android_keystore: androidReleaseKeyStore
      android_keystore_password: androidReleaseKeyStorePassword
      android_key_alias: androidReleaseKeyAlias
      android_key_password: androidReleaseKeyAliasPassword

  - name: Verify signed APK was produced
    run: |
      set -euo pipefail
      out="${{ github.workspace }}/signed-apks/${{ matrix.artifact }}.apk"
      [[ -f "$out" ]] || { echo "::error::signing-service did not produce $out"; exit 1; }
      [[ -s "$out" ]] || { echo "::error::signed APK is empty: $out"; exit 1; }
    shell: bash
```

iOS resign job 同理:

```yaml
- name: Prepare workspace
  run: |
    set -euo pipefail
    rm -rf "${{ github.workspace }}/unsigned"
    rm -f  "${{ github.workspace }}/TDWealth_${{ matrix.configuration }}-${{ matrix.platform }}.ipa"
  shell: bash
```

## P2-1 · publish 发布目录清理 + manifest 反向校验(Android)

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
    clean: true

- name: Clean publication output dir
  # skipPublicationBuild=true 会原样发布该目录内容,
  # 这里不允许存在任何非本次 restore 写入的文件
  run: rm -rf app/build/outputs/apk signed-apks unsigned-apks
  shell: bash

- name: Download signed APKs
  uses: actions/download-artifact@v4
  with:
    pattern: signed-*
    merge-multiple: true
    path: ${{ github.workspace }}/signed-apks

- name: Download APK manifest
  uses: actions/download-artifact@v4
  with:
    name: unsigned-apks
    path: ${{ github.workspace }}/unsigned-apks

- name: Restore signed APKs to publication paths
  run: |
    set -euo pipefail

    while IFS=$'\t' read -r name relpath; do
      [[ -z "$name" ]] && continue
      src="signed-apks/$name.apk"
      dest="app/build/outputs/apk/$relpath"
      [[ -f "$src" ]] || { echo "::error::Signed APK missing: $src"; exit 1; }
      mkdir -p "$(dirname "$dest")"
      cp "$src" "$dest"
    done < unsigned-apks/manifest.tsv

    # 反向断言:发布目录里不能多也不能少
    expected=$(cut -f2 unsigned-apks/manifest.tsv | sed 's|^|app/build/outputs/apk/|' | sort)
    actual=$(find app/build/outputs/apk -name '*.apk' -type f | sort)
    if [[ "$expected" != "$actual" ]]; then
      echo "::error::Publication dir contents do not match manifest"
      diff <(echo "$expected") <(echo "$actual") || true
      exit 1
    fi
  shell: bash
```

## P2-2 · Locate IPA 改为断言(iOS,两处)

```yaml
- name: Locate Unsigned IPA
  id: locate-ipa
  working-directory: ${{ github.workspace }}
  run: |
    set -euo pipefail
    ipa_count=$(find dist -name '*.ipa' -type f | wc -l | tr -d ' ')
    if [[ "$ipa_count" -ne 1 ]]; then
      echo "::error::Expected exactly 1 IPA under dist/, found $ipa_count"
      find dist -name '*.ipa' -type f
      exit 1
    fi
    echo "ipa_path=$(find dist -name '*.ipa' -type f)" >> "$GITHUB_OUTPUT"
  shell: bash
```

resign job 里把 `dist` 换成 `unsigned`。

## P2-3 · baseline 固化为 job output(Android)

`build` job 加:

```yaml
outputs:
  artifact_suffix: ${{ steps.branch.outputs.artifact_suffix }}
  additional_params: ${{ steps.branch.outputs.additional_params }}
  baseline_commit: ${{ steps.baseline.outputs.baseline_commit }}
```

```yaml
- name: Get Baseline Commit
  id: baseline
  env:
    GH_TOKEN: ${{ github.token }}      # 不再内联进命令行,避免 ps 泄漏
  run: |
    set -euo pipefail
    BASELINE_COMMIT=$(bundle exec github-baseline-commit \
      -t "$GH_TOKEN" \
      -r "${{ github.repository }}" \
      -w "${{ github.workflow_ref }}" \
      -h "${{ github.sha }}")
    echo "baseline_commit=$BASELINE_COMMIT" >> "$GITHUB_OUTPUT"
  shell: bash
```

publish job 删掉自己那份 `Get Baseline Commit`,改用 `${{ needs.build.outputs.baseline_commit }}`(已写在 P0-2 的 env 里)。

> 注意:这一步依赖 `bundle install`,所以要放在 build job 的 Bundle Install 之后。

## P2-4 · Stage 免 jq 生成 matrix 列表(Android,bash 3.2 兼容)

```bash
list=$(cut -f1 unsigned-apks/manifest.tsv | sed 's/.*/"&"/' | paste -sd, -)
echo "artifact_list=[$list]" >> "$GITHUB_OUTPUT"
```

## P3 · 显式化与语法加固

```yaml
- uses: actions/checkout@v4
  with:
    fetch-depth: 0
    # 显式声明:self-hosted runner 工作区跨 run 复用,
    # 本流程的 unzip / dist / app-build-outputs 均依赖此处清理。
    # 如需为提速关闭,必须先落实上面各处显式 rm -rf。
    clean: true
```

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}-${{ github.event_name }}
  cancel-in-progress: true
```

```yaml
jobs:
  build:
    timeout-minutes: 120   # iOS 用 90;xcodebuild/fastlane 偶发挂死需兜底
```

所有多行 `run:` 统一开头加:

```bash
set -euo pipefail
```

（GitHub 对 `shell: bash` 默认只给 `-e`,不给 `-o pipefail`,而这两份 workflow 里 `cmd | head -1`、`grep | cut | head` 这类管道用得不少。）

**bash 3.2 禁用清单**(mac runner 的 `/bin/bash`):`mapfile` / `readarray`、`${var,,}` / `${var^^}`、`declare -A`、`**` globstar,以及 `jq`(非自带)。