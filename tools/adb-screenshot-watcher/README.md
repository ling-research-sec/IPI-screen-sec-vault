# Android ADB Screenshot Watcher

轻量级 Python 桌面工具：监测 Android **实际保存的新截图文件**，通过 ADB 原样复制到电脑，保留 JSONL 证据清单。提供 CLI 和 Tkinter GUI，运行时仅使用 Python 标准库和 Android Platform Tools。

不需要 Root、不安装 APK、不调用 OCR / AI / 网络 API、不生成截图、不转换或压缩图片、不删除或写入手机文件。源文件只通过目录读取、`stat`、`sha256sum` 和 `adb pull` 访问；不调用 `kill-server`，不接管其他 ADB 工具。

## 快速开始

需要 **Python 3.10+（含 Tkinter）** 和 [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)。手机开启 USB 调试并在手机上确认授权。macOS 和 Windows 11 使用相同的 Python 模块；Windows 实机验证状态见[测试报告](TEST_REPORT.md)。

先在本工具目录打开终端：

```sh
python3 -m tkinter
adb version
python3 -m screenshot_watcher devices
```

Windows 将 `python3` 换成 `py -3`。本项目不需要 `pip install`；`requirements.txt` 仅说明外部运行条件。

### GUI

- macOS：双击 `start-macos.command`，或执行 `python3 -m screenshot_watcher gui`。
- Windows 11：双击 `start-windows.bat`，或执行 `py -3 -m screenshot_watcher gui`。
- 选择目标设备、保存目录，点击“开始监听”。**等日志显示“基线完成”后，再手动截图。**
- “停止监听”结束当前会话；再次开始创建新会话、重新建立基线，排除停止期间产生的截图。
- 设备列表显示 `unauthorized` 时在手机确认授权；`offline` 或断线时保留所选 serial 等待恢复，不自动改用另一台手机。闲置时可点击“刷新设备”。
- 默认轮询 0.5 秒；可在界面修改。自定义目录留空则自动发现，多个截图专用目录用分号分隔。

### CLI

```sh
# 只读检查目录、已有文件数、一个已有文件的哈希及设备时钟
python3 -m screenshot_watcher inspect --serial SERIAL

# 开始监听；Ctrl+C 正常结束
python3 -m screenshot_watcher watch --serial SERIAL --output captures

# 可重复传入自定义截图专用目录；替代自动发现
python3 -m screenshot_watcher watch --serial SERIAL \
  --remote-dir /sdcard/Pictures/Screenshots \
  --remote-dir /sdcard/DCIM/Screenshots \
  --interval 0.5 --stable-for 0.5 --output captures

# ADB 不在 PATH 时，全局 --adb 参数放在子命令前
python3 -m screenshot_watcher --adb /path/to/adb devices
```

启动脚本也支持 `ADB` 环境变量指定可执行文件；macOS 另支持 `PYTHON` 指定 Python 路径。Windows 可用 `set "ADB=C:\Android\platform-tools\adb.exe"` 后运行脚本。只有全局枚举 `adb devices -l` 不带 `-s`；所有设备操作都固定为 `adb -s SERIAL ...`。[ADB 官方说明](https://developer.android.com/tools/adb)

## 采集行为

1. 检查 `/sdcard/Pictures/Screenshots`、`/sdcard/DCIM/Screenshots`，两者都监听；使用 `readlink -f` 消除路径别名。未建立的优先目录也会继续检查。
2. 若两个优先目录都不存在，尝试 MediaStore `_data` 查询，寻找含 Screenshot / 截屏 / 截图的目录。ROM 拒绝查询时给出日志；可使用 `--remote-dir`。**不承诺枚举所有 ROM 路径**，自定义目录是确定性入口。
3. 首次成功扫描建立基线，记录路径、大小、inode、mtime / ctime（含纳秒文本），并在手机端为基线文件计算一次哈希，避免历史文件被延迟的 MediaStore 元数据更新误导入。已有截图不下载；历史图片多时，基线准备耗时会增加。
4. 对新增或替换版本连续观察至少两轮，且元数据稳定至少 0.5 秒、大小大于零，才尝试下载。
5. 前后核对源元数据及手机 SHA-256，下载至本地 `.part`，检查字节数和本地 SHA-256。成功后同步文件并原子重命名，最后同步成功日志。
6. 同名但内容不同的文件版本独立保存；路径、inode、mtime 纳秒、大小及 ctime 区分版本。仅 ctime 变化且哈希相同的已知版本不重复保存。不同路径的两张截图即使字节相同也分别保留。
7. 失败清理临时文件、记录 `failed`，按 1、2、4……最多 30 秒间隔重试，不影响其他文件继续处理。若磁盘连失败日志都写不下，会在界面 / 控制台显示错误并继续重试，不伪记成功。

**停止与断线不同：**主动停止后重新开始会排除期间的截图；短暂断线不结束会话、不重建基线，重连后可收集断线期间仍留在手机上的新截图。退出时取消本工具发起的 ADB 客户端并等待后台线程结束；保留共享 ADB 服务。

## 保存与证据

```text
captures/
  session_YYYYMMDD_HHMMSS/
    0001_YYYYMMDD_HHMMSS_ffffff.png
    0002_YYYYMMDD_HHMMSS_ffffff.jpg
    manifest.jsonl
    session.json
```

保留原始扩展名及原始字节，不重新编码。支持 PNG、JPEG、WebP、HEIC、HEIF、AVIF、BMP、GIF。监听目录的直接子文件，不递归收集其他相册。会话同秒启动会追加目录后缀；序号分配给每次传输尝试，失败会留下序号空档，GUI 数量只统计成功文件。

每行 `manifest.jsonl` 必含：`sequence`、`device_serial`、`detected_at`、`source_path`、`local_path`、`file_size`、`sha256`、`transfer_status`、`error_message`。失败记录的 `local_path` / `sha256` 为 `null`。成功行另含手机哈希、源元数据、`saved_at` 及延迟字段。清单时间为带时区 UTC；目录和文件名采用电脑本地时间。

- `detection_to_saved_seconds`：电脑首次观察到文件至本地图片原子发布的单调时钟耗时，包括稳定检查、排队及重试。
- `source_mtime_to_saved_seconds_estimate`：源文件最后修改时间到本地发布的估计，使用采集开始 / 重连时的设备时钟往返校准；另记录 `clock_uncertainty_seconds`。设备时钟后续漂移不包含在该不确定度内。
- mtime **不是精确创建时间或按截图键的时刻**。测试手机不提供文件 birth time，报告不将此估计冒充“创建到保存”的精确延迟。

macOS 使用 `renamex_np(RENAME_EXCL)`，Windows 使用不覆盖目标的 `os.rename`。临时文件与最终文件在同一目录；若目标已存在则报错重试，不覆盖。[Apple 标志定义](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/stdio.h)

## 测试

```sh
python3 -m unittest discover -s tests -v
# 需要桌面显示环境；使用虚拟 ADB，不访问手机
PYTHONPATH=. python3 tests/gui_smoke.py
```

Windows GUI 冒烟测试可使用 PowerShell：

```powershell
$env:PYTHONPATH = "."
py -3 tests/gui_smoke.py
```

真机交互测试（仅在用户手动截图时收集，不主动生成图片）：

```sh
PYTHONPATH=. python3 tests/gui_live.py --serial SERIAL
python3 tests/verify_captures.py --serial SERIAL --captures captures
```

详细结果、A–H 验收、测量边界见 [TEST_REPORT.md](TEST_REPORT.md)。

## 已知边界

- 轮询只能发现至少在某次扫描时仍存在的文件；两轮扫描之间被外部程序覆盖 / 删除的中间版本无法事后还原。纯轮询不承诺任意频率、任意生命周期下零丢失。
- 0.5 秒是轮询周期下限，不是交付延迟保证。目录扫描、手机存储、USB、校验及重试都会增加耗时；传输串行以减少设备和桌面负载。
- 稳定观察不能证明未来永不再写；前后哈希和元数据核对用于拒绝本次传输中的变化。发布后产生的新内容版本会再次采集。
- 需要设备 shell 能读取截图目录，且提供 `stat -c`（含 `%y/%z`）和 `sha256sum`。尚未解锁的加密存储、ROM 特有权限、MTP 可见但 ADB 不可读的文件需要单独验证。
- 普通退出会清理临时文件；断电 / 强制结束可能留下 `.part`，它们不会被登记为成功或在下次启动导入。图片原子发布和 JSONL 追加不构成跨文件的断电事务；断电窗口内可能出现未登记的完整图片，应保留并人工核查。
- 不使用全局内容哈希去重，以免丢弃不同截图文件。重命名为不同路径按新路径处理。
- Windows 11 和双物理设备尚待实机补验；当前已完成 macOS 单真机及离线多设备路由测试。未执行数小时 / 数天耐久测试。

## 模块

- `screenshot_watcher/adb.py`：ADB 调用、设备枚举、目录发现、元数据和哈希读取。
- `screenshot_watcher/watcher.py`：轮询、基线、稳定判断、版本去重、重连及重试。
- `screenshot_watcher/storage.py`：原始文件保存、原子发布及 JSONL。
- `screenshot_watcher/gui.py`：Tkinter 界面，后台线程不直接操作控件。
- `screenshot_watcher/__main__.py`：CLI 和正常退出处理。
