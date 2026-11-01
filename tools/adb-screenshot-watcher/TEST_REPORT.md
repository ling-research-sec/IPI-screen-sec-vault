# Android ADB Screenshot Watcher 测试报告

日期：2026-10-31（Asia/Taipei）。仅实际观察到的结果记为通过，模拟与真机结果分开列示。

## 环境与范围

- macOS 27.0.1 / Apple Silicon；Python 3.14.6；Tk 9.0；ADB 37.0.0-14910828。
- 一台 Android 16 / SDK 36 手机，型号 2106118C，serial `75ea8363`。
- 发现 `/sdcard/Pictures/Screenshots`，规范化为 `/storage/emulated/0/Pictures/Screenshots`；另一个优先目录保留监测。
- 手机支持纳秒 `stat`、`sha256sum` 和 `date +%s.%N`；`stat %W/%w` 返回 `?|?`，没有可用 birth time。
- 未安装 APK、未取得 Root、未修改手机设置、未主动触发截图、未向手机写入或删除文件。所有新增截图都由用户手动产生。
- 原有仓库文件未改；新增内容仅位于本工具目录，未提交或推送 Git。

## A–H 验收

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| A 监听后手动截一张 | 真机通过 | 第一会话第 1 张成功；手机 / 本地 SHA-256 一致 |
| B 连续截 10 张 | 真机通过 | 同会话另 10 张成功；总计 11 个不同源路径、11 份完整文件，0 失败、0 重复 |
| C 停止期间截图不导入 | 真机通过 | SIGTERM 正常停止；用户截 1 张；重新开始时基线为 15，成功数仍为 0 |
| D 恢复监听采集新图 | 真机通过 | 第二会话开始后手动截 1 张，成功数变为 1；停止期间那张未出现于任何成功清单 |
| E 拔线再连接不崩溃 | 真机通过 | 20:20:21 报 device not found；原进程仍存活；20:21:04 恢复监听；重连后的新图成功保存 |
| F 同接两台，指定目标 | 自动化通过；双真机待验 | 模拟 A/B 两台设备，只对 B 发出 `adb -s B get-state`；现场仅接一台，不宣称双物理设备通过 |
| G SHA-256 一致 | 真机通过 | 14 张成功文件逐张与手机源文件重新计算比较，14/14 一致，0 个完整性错误 |
| H 原图不删除 / 不修改 | 真机通过（已检查字段） | 最初 3 张原图的内容哈希、大小、inode、mtime / ctime 含纳秒均保持一致；全部 14 张采集源文件仍在且哈希一致 |

读取行为可能由文件系统更新访问时间 atime；本工具不主动改动手机文件。H 的比较不将 atime 纳入“未变更”结论。

### 真机会话

| 本地会话 | 基线数 | 成功数 | 失败尝试 | 用途 |
| --- | ---: | ---: | ---: | --- |
| `session_20261031_201751` | 3 | 11 | 0 | A、B |
| `session_20261031_201930` | 15 | 2 | 0 | C、D、E |
| `session_20261031_202221` | 17 | 1 | 1 | GUI 原始文件采集、源元数据变化重试 |
| `session_20261031_202559` | 18 | 0 | 0 | 最终代码真实基线、历史不回采、正常退出复测 |

GUI 会话首次尝试发现源文件 ctime 由 `.083239427` 变为 `.087239427`，将该次记为 `failed`，清理临时文件后重试。第二次成功：仅保存 1 份文件，文件名从 `0002_` 开始，GUI 成功计数为 1。失败序号不是丢图。

## 实际延迟与测量边界

最新 GUI 样本：

- 首次检测：`2026-10-31T12:22:38.638+00:00`。
- 本地原子发布：`2026-10-31T12:22:41.525+00:00`。
- **检测到文件 → 本地保存：2.886345 秒**，单调时钟测量，含稳定检查及一次重试。
- 源 mtime：`2026-10-31 20:22:38.071239427 +0800`。
- 设备相对电脑时钟估计偏移：`-0.21915793418884277` 秒。
- **源 mtime → 本地保存估计：3.234612 秒**；往返校准模型的不确定度约 0.053844 秒，不含设备时钟后续漂移与 mtime 语义偏差。

**本样本未达到约 1 秒目标。** mtime 是最后写入时间，既非按键时刻，也不等价于文件创建时刻；该手机未提供 birth time，因此没有“精确创建到保存延迟”的实测结论。每条成功日志仍保留两个延迟字段供后续分析，未用假定的 1 秒值填补数据。

首轮 CLI 的历史日志记录检测至保存为 0.825064～2.061706 秒。该轮运行后发现批量循环可能在前一张下载后才登记后续文件的墙钟检测时间；已修复为先登记整轮快照、再进行传输。原始日志不改写，最终计时展示采用修复后的 GUI 样本，不混合计算“最终版本批量延迟”指标。

## 自动化验证

```sh
python3 -m unittest discover -s tests -v
# Ran 43 tests ... OK，exit 0

PYTHONPATH=. python3 tests/gui_smoke.py
# GUI_SMOKE PASS: refresh/start/count/latest/stop/close; no worker leak
# exit 0

python3 tests/verify_captures.py --serial 75ea8363 --captures .evidence-captures \
  --report evidence/capture-integrity.json
# verified=14, failed_attempts_logged=1, integrity_errors=[], result=PASS
# exit 0
```

43 项测试覆盖：初始基线、延迟的历史 ctime 更新、同名同大小同秒不同纳秒、相同 mtime 但内容变化、晚到的 ctime 更新不重复保存、不同图片相同字节不丢弃、10 图一次性保存、写入增长、空文件、写入稳定、传输期间源变化、局部传输失败继续其他文件、指数重试、哈希不一致拒收、临时文件清理、磁盘 / manifest fsync 失败不留下虚假成功记录、目标已存在时禁止覆盖、会话目录冲突、主动停止重建基线、断线恢复不重建基线、unauthorized / offline、扫描失败保留基线、shell 路径转义、NUL 分帧、MediaStore 回退、自定义目录、精度与时钟回退、多设备路由，以及实际子进程超时 / 取消后的回收。

GUI 冒烟测试使用真实 Tk 窗口与虚拟 ADB，验证设备刷新、开始、计数、最新文件、停止、关闭和线程回收；GUI 真机测试另外完成 1 张图片采集。后续增加的基线哈希、ctime 去重和 manifest 同步失败修复已重新跑全部单元测试、GUI 冒烟和最终真机空闲监听，不将前期真机采集冒充这些新增边界的真机故障注入。

最终 CLI 真机空闲监听结果：`baseline=18; history imports=0; graceful SIGTERM exit=0`。所有测试监听进程已停止，手机保持连接；没有遗留本工具的 ADB 子进程。

## 文件与原始证据

工具根目录：`/Users/y4n9/Workspace/Projects/My-github-projects/IPI-screen-sec-vault/tools/adb-screenshot-watcher`。

- `evidence/environment.json`：真实环境。
- `evidence/device-inspect.json`、`device-inspect-final.json`：只读目录检查。
- `evidence/device-before.json`、`device-after.json`、`source-preservation.json`：原图哈希与元数据比较。
- `evidence/capture-integrity.json`：逐张复核结果。
- `evidence/unit-tests.txt`、`gui-smoke.txt`、`gui-live.txt`、`cli-final-idle.txt`：测试记录。
- `.evidence-captures/session_*/`：原始下载文件、manifest 及 session 信息，未改写。图片保持本地，不纳入轻量交付 ZIP。
- `evidence/BASELINE.txt`：开发前本工具不存在的状态记录；原始 SHA-256：`ae4bdb1002a3028b384fc26052f3be2fac4acb9a44ea7f48596dfdd2e2b0722a`。
- `evidence/DIFF_FILE.patch`、`evidence/VERIFICATION.txt`、`evidence/ROLLBACK.sh`：新增文件差异、命令 / 结果及经过副本验证的回滚入口。回滚只移除交付代码文件，保留采集图片和证据，遇到代码被再次修改会先终止，避免覆盖后续工作。

## 待补验与剩余风险

1. **Windows 11 真机、双物理设备**：未执行，仍需使用 README 中命令补验，不能由路由模拟替代。
2. **其他 ROM / 权限 / 图片格式**：MediaStore 和特殊路径目前由单元测试覆盖，现场 ROM 只验证自动发现的主截图目录及实际 PNG；已有 JPEG 仅只读检查及哈希。标准库不解析图片，完整性以大小和哈希为依据。
3. **长时间运行**：已做数分钟交互、断线恢复和自动化回归，未做数小时 / 数天耐久及数万文件性能测试。
4. **轮询边界**：文件在扫描之间被外部删除或反复覆盖时，无法还原未观察到的版本；重命名为新路径按新文件处理。大量历史文件增加初始基线哈希及每轮 stat 的成本。
5. **断电与磁盘故障**：普通失败和 fsync 失败已做模拟；突然断电 / 强杀的跨文件事务不作保证，可能留下 `.part` 或未登记完整文件；不自动删除这些证据。
6. **延迟目标**：实测值如上，没有承诺全场景小于 1 秒。后续优化以保留校验与证据为前提，不牺牲完整性换取表面速度。
