# IPI Surface Lab

Android 第三方 App 数据面测试工具，当前版本 **0.1.2**。实际调用系统 API，记录创建、查询、修改和人工观察；不自动操作 AI 助手。

## 安装与使用

下载 [Debug APK](dist/IPI-Surface-Lab-debug.apk)，Android 10 / API 29 以上可安装。也可通过 ADB 安装：

```sh
adb -s SERIAL install -r dist/IPI-Surface-Lab-debug.apk
```

首页点“新 Run”→ 填写并保存 Global Payload → 进入模块 → 套用 Payload、申请所需权限 → 执行并查询结果。系统操作和人工 AI 观察分别保存，首页可导出 JSON / CSV。

| 模块 | 功能 |
|---|---|
| 联系人 | 创建、查询、修改自建测试联系人；通过系统选择器选择已有号码，单独修改、查询、恢复原号码 |
| 通知 | 普通、长文本、聊天通知；更新、查询本 App 活跃通知、取消 |
| 日历 | 选择可写 Calendar ID，直接创建/查询/清理测试事件；也可打开系统确认入口 |
| 闹钟 / 计时器 | 向系统时钟传递时间和标签；实际创建情况需在系统时钟核实 |
| 文件 | 生成 TXT、HTML、两段分页 PDF；查看 SHA-256、分享、SAF 导出 |
| Screen / Assist | 原生 TextView 页面；分别配置可见文字、Assist Bundle 和 JSON-LD，并记录系统回调 |

### 修改已有联系人号码

“选择已有联系人号码”→ 选择一条号码 → 输入新号码 → “修改选中的已有号码”。只修改选中的号码，不覆盖姓名或其他号码；可查询或恢复选择时的原号码。此入口不要求联系人由本 App 创建。

重新选择会建立新的恢复基线；如果所选行已被其他应用改变，先核实再操作。外部选中的联系人不加入模块清理列表。

### 结果怎么看

- `VERIFIED`：对应查询或读回成功，不代表 AI 已读取或执行。
- `CREATED / POSTED`：本地创建或通知提交。
- `PENDING_USER_ACTION / UNKNOWN`：需要系统确认或结果尚未确证。
- `PERMISSION_DENIED / UNSUPPORTED / FAILED`：查看结果中的原因。

本机真机已验证联系人创建及自建字段修改、通知、日历创建、文件生成和闹钟确认流程。**已有号码修改目前通过模拟器测试，真机仅确认新版安装及入口显示；Assist 交付在测试接收器上验证，不代表商业助手消费。**

## 开发与测试

Kotlin + Compose Material 3；JDK 17、Gradle 8.14、AGP 8.13.2；minSdk 29，compileSdk / targetSdk 35。

配置 `ANDROID_HOME` 或本机 `local.properties` 后，在工程目录运行：

```sh
./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
ANDROID_SERIAL=emulator-5580 ./scripts/test-emulator.sh
python3 scripts/package.py
```

18 项仪器测试覆盖系统 Provider、通知、文件、持久化、已有号码修改/恢复和冲突保护；另有 4 项单元测试。[真机测试步骤](TEST_PLAN.md)。可选 Assist/UI 脚本只针对名为 `IPI_Surface_Lab_API35` 的一次性 Pixel 7 模拟器，输出留在本地 `evidence/`。

## 数据与清理

无 INTERNET 权限，数据默认留在本地；联系人、日历、通知权限按模块申请。号码默认留空，不自动拨号或发短信。

清空日志不删除对象登记表。模块清理会处理该模块**所有已登记的自建测试对象**；系统 Intent 创建项、闹钟和 SAF 副本需人工清理。卸载前先处理需要保留或清理的数据。
