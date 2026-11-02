# 实验工具

| 工具 | 用途 | 入口 |
| --- | --- | --- |
| [Android Screen Readability](android-screen-readability/SKILL.md) | 可配置的 Android 识读实验采集、评分与报告 pipeline | `android-screen-readability/scripts/pipeline.py` |
| [ADB Screenshot Watcher](adb-screenshot-watcher/README.md) | 监听并校验手机新截图，提供 CLI 和桌面窗口 | `adb-screenshot-watcher/start-macos.command` / `start-windows.bat` |
| [GPT Advanced 单张执行](gpt-advanced-single/README.md) | macOS 上的选图、共享、提示词播放、回答截图及可选循环 | `gpt-advanced-single/start.command` |

按需选用，不必同时启动。设备、界面与系统依赖及验证边界见各自说明。

## 提交范围

保留源码、启动脚本、离线测试、使用说明和运行必需资源（如提示词音频与 HTML 页面）。截图、设备信息、运行日志、验收证据、缓存及交付 ZIP 留在本地，不随工具提交；实验数据由仓库其他目录单独管理。
