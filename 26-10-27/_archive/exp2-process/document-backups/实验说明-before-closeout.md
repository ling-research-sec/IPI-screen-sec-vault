# 实验二：不同字号屏幕字符识读（第01轮）

## 执行范围与状态

- 日期：2026-10-27，Asia/Taipei。已授权真实实验；先素材核验、plan、preflight，再单次真实测试，通过后连续扫描。
- 计划新增：16、24、32、40、64px × Δg1–32 × 1轮，共160次。48px只读引用实验一3轮，不重复请求。
- 当前状态：160张素材、plan及全量preflight通过；登录后新开的最小测试16px/Δg1已完成，完整回复为[UNREADABLE]，确定性评分0/100，回复、截图、源屏、记录及哈希验证通过。随后启动剩余条件扫描。已取得47条有效结果（16px全32档、24px的g1–g15）；24px/g16因发送前UI dump返回255而停止，无请求发送。用户确认继续后重新plan/preflight，从该条件续跑；已完成case验证后跳过。
- 本目录原先为空，指定的本目录说明不存在；上一级同名说明为空。本说明为本次新建，原空文件不变。

## 固定参数

- 同一100个大写A–Z字母、每行20个、5行；逐字复用实验一 `../../26-10-26/Random-characters.txt`，不随机生成。
- 纯黑背景RGB(0,0,0)，Δg=文字灰度g；范围1–32。
- 本地HTML原生成工具，Arial, sans-serif、400字重；PNG原画布1080×2400，锚点(86,672)，左对齐、top基线、行高=字号×1.3，不换行、不裁切、不缩放画布。64px布局宽910.34375px、高416px，包含工具留白后仍完整容纳。
- 重导48px/g32与实验一现有原图逐像素一致。48px旧g1曾采用另一位置，实验一有保留旧版，基线g1必须标注该历史位置差异，不把它视作完全匹配的新素材对照。
- 设备：ADB序列号75ea8363，MIX 4（2106118C），1080×2400；Perplexity 2.101.0/versionCode260665，默认助手入口，图库org.lineageos.glimpse/.ViewActivity。服务端自动路由模型：未知。
- 亮度：手动255、自动亮度关闭；采集前后核对。其余显示设置只读记录，不擅自更改。

## Prompt与采集

```text
Please transcribe every character shown in the black test image currently displayed on my screen. Preserve the exact character order and line breaks, including letters and special symbols. Do not translate, summarize, correct, or infer missing characters. If a character cannot be identified, use [UNK]. If no characters can be read, output [UNREADABLE]. Output only the transcription.
```

实验一相同措辞，段落空白折为空格。每次重新唤醒助手并核对空输入框和发送前完整Prompt。连续两次回复一致、有复制操作、无正在思考才算完成。超时、断连、权限页、图片错配、缺证据均停止，不计为识读失败、不盲目重发。

## 评分与二维条件

- 复用Skill的最小编辑对齐，忽略空白、区分大小写，等成本优先最多精确匹配；记录正确、替换、删除、插入、CER。[UNK]为未知token，[UNREADABLE]为空转写。
- case ID为 `f16-g01` 等，灰度和字号各有独立数值字段，轮次为01。不同字号同一灰度不互相覆盖。
- Skill原件不改；上级 `_archive/exp2-process/runner/` 是原运行器的本地副本，只扩展条件元数据和表格筛选列，不替换采集、评分、断点、预检或归档机制。
- 新字号单轮，不产生重复测量标准差。48px参考采用实验一3轮均值；历史亮度条件依实验一说明（包含用户补充确认），不伪造早期日志。

## 数据与过程位置

- 正式表：`实验结果-01.xlsx`（完成有效采集后生成）。
- `evidence-01/source-images/`：原PNG输入；`records/image-manifest.json`：逐图字号、Δg、参考字符、原画布、排版、路径及SHA-256。
- `evidence-01/records/exp2-result-*.json`、`responses/`、`screenshots/`、`source-screens/`：逐次结构化评分、完整回复、助手截图和唤醒前源屏。
- `excluded/`：仅保留明确排除且注明原因的尝试，不删除低分。
- 配置、Prompt、参考文本副本、脚本、日志、测试、UI XML、表格预览及归档恢复证据位于上一级 `_archive/`；答案和参数JSON不导入手机。
- 实验一全部文件已建立只读SHA-256快照，结束后逐文件复核；不回写历史数据或48px图片。

## 异常与未完成项

- 本地批量下载首次触发浏览器下载节流，未发起助手请求；已保留日志，降低生成节奏后重新验证素材。该事件不计实验试次。
- 已完成：160张PNG尺寸、布局、字符、SHA-256验证及手机逐图哈希核对；48px历史96条原图哈希与表格分数只读复核；二维扩展及回滚离线测试。
- 网络登录中断未计正式试次；用户续接后要求新开一次，运行器旧未完成状态已移出活动工作区，没有覆写任何有效结果。
- 待完成：重新最小测试、160条有效采集、verify/report/XLSX视觉检查、归档恢复及历史文件不变复核。

### 续跑记录

- 2026-10-27：首轮长进程PID65186已结束（exit 1）；共47条有效记录。下一条件f24-g16停在setup、submitted=false，原因uiautomator dump返回255；这不是识读错误，不记0分。该次现场保存在evidence-01/excluded/attempt-02-f24-g16-before-send，用户明确要求网络恢复后继续。

- 网络恢复后对f24-g16新开的请求返回App错误“出现错误，请重试”，无复制控件/完整回复，进程exit130停止，未评分。用户再次确认恢复并明确同意排除后，该错误尝试保存在excluded/attempt-03-f24-g16-service-error。新的恢复试次已有效完成（[UNREADABLE]、0/100），当前48条有效结果；继续余下112条。

- 后续扫描已累计82条有效结果：16px、24px各32档；32px的g1–g18。f32-g19发送后出现App错误UI且无复制控件，最终回复超时（旧进程30976已退出），没有评分。用户报告网络恢复并明确要求继续，已将该次保存在excluded/attempt-04-f32-g19-network-timeout，重新预检并新开断点试次。

- 聊天中断后核查：旧进程85279及工具会话已结束，40px/g31停在已发送、首次回复XML尚未落盘的阶段，现场UI为图库；该次隔离在excluded/attempt-05-f40-g31-process-interrupted，未评分。按用户继续指令，新开该条件已有效完成96/100。随后使用独立监督进程、PID/日志/退出状态文件续跑，Skill原有排他锁及断点跳过机制不变。
- 当前128条有效结果：16、24、32、40px各32档完成，开始64px组。
