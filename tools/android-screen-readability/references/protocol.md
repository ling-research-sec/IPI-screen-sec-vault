# 配置和运行契约

## 配置

从`example-config.json`复制到用户指定临时/过程目录，替换示例路径和序列号。样例不是执行授权。

- `experiment_dir`、`reference_file`、`prompt_file`为绝对路径。参考文件首尾空行不作展示字符；内部空白按`whitespace`处理。
- `image_pattern`、`phone_image_pattern`支持`{value}`和`{id}`。先导入PNG并加入MediaStore；运行器核对手机文件SHA256，不自动上传答案文本。
- `values`是本次要执行的参数值，不是总覆盖范围；`rounds`是轮次。值需唯一，ID不含路径分隔符。一个实验默认只扫一个变量。
- `parameter_key/label`例如`gray/名义灰度`或`font_px/字号(px)`。`font_px`和`report_context`描述原图，不等同于落屏字号。
- `artifact_stem`默认为`exp1`，对应`exp1-result-1.json`、`exp1-response-1.txt`、`exp1-screenshot-1.png`，同一实验保持稳定。
- `brightness.action=manual`只有在`run --execute`时才关闭自动亮度并设置0–255目标值；`preserve`不调亮度并记录设置。预检只读。
- `whitespace`支持`ignore`（默认）、`linebreaks-only`、`preserve`；有意义的空格不能用默认忽略规则。
- 英文Prompt通过ADB输入前合并段落空白，完整措辞经UI核对后才发送。v1不处理非ASCII提示词和字面量`%s`，不自动安装输入法。
- `legacy_condition_label`可为没有机器亮度日志的旧记录提供有来源的显示标签，例如“最大亮度（用户确认）”。不伪造观测，已有表格中的旧标签优先保留。

## 已验证适配

Perplexity Android versionCode260665，中文UI、默认助手入口；1080×2400手机键盘入口坐标(99,2280)，图库为`org.lineageos.glimpse/.ViewActivity`。这些是当前真实样例的配置，不是所有手机通用事实。

尺寸、App版本、默认助手或前台Activity不同就停止，不自动切换角色或点击授权页。换手机/App/语言时，先读包、角色、界面，受控验证入口、发送控件和完成标志，再更新配置或新增适配。Perplexity坐标不能直接套给Gemini/Orbit。

`Device`封装ADB/XML/截图，`run_trial`封装当前App顺序。增加App时在这一层分离适配，复用证据、评分、报告模块。结构或模拟测试不代替新App端到端验证。

## 命令

`S`表示Skill绝对路径，`C`表示配置绝对路径：

```sh
python3 "$S/scripts/pipeline.py" plan "$C"
python3 "$S/scripts/pipeline.py" preflight "$C"
# 明确开工后：
python3 "$S/scripts/pipeline.py" run "$C" --execute
# 离线评分，默认只打印汇总；指定--output才写完整中间数据：
python3 "$S/scripts/pipeline.py" score "$C"
python3 "$S/scripts/pipeline.py" score "$C" --output /ABS/TEMP/scores.json
# 使用load_workspace_dependencies返回的Node路径，并遵循Spreadsheets skill的操作标记：
python3 "$S/scripts/pipeline.py" report "$C" --execute --node "$NODE" --node-modules "$MODULES"
python3 "$S/scripts/pipeline.py" verify "$C"
python3 "$S/scripts/pipeline.py" archive "$C" --execute
```

`report/verify --output-dir /ABS/TEMP/report`用于隔离验证，不覆盖原表。新建为两页签黑白表格，兼容已有`A9:I...`布局。旧分数/原文不一致或模板不同会停止，不擅自重建或覆盖。

报告包含指定轮次目录中全部已完成试次，但要求本次`values`均已完成。追加仅加新档位，保留旧行、原文和条件标签。完整重算旧评分须明确请求和复核，不能借追加悄悄重算。

## 状态与证据

结果记录最后原子写入。完成试次校验后跳过；图像、Prompt或参考变了则不是相同试次，需新轮次/新协议。

工作目录在上一级`_archive/.<实验名>-screen-readability-work/`，有所有权标记和排他锁。发送前先落盘`submitting`；崩溃后不盲目重复请求，未完成状态需人工判断。

先轮询原工具进程句柄；确认已结束后才处理残留状态。明确无效时，把该case工作目录、外部`source-screens/gID-source-clean.png`及已有回复/结果截图一起留在`excluded/`，注明原因与是否已发送。不把超时算看不见，不删低分重测。

正式记录含输入/参考/Prompt哈希、实际亮度、原回复、图片哈希、UI及不可变协议快照的归档成员。`ui_archive`相对于实验根目录，PNG/TXT路径相对于本轮证据目录。用户确认不回填成早期机器日志。

工作目录的`protocols/`按内容哈希保留每份配置、参考文本和原Prompt，后续调用不会覆盖旧协议。旧图/旧文本改变后不要复用原case。表格中的公式样式字符串会按字面量转义，原TXT和JSON仍保持原文。

`archive`在验证表格、所有工作状态完成后打包。包内保留UI XML、提示词截图、配置、参考文本、原表备份、预览及哈希清单；独立恢复校验后才删除自己的工作目录。外部依赖仅保存链接，不打包或删除依赖目标。手机临时XML已归档后可按固定名清理，不清理素材。

## 素材和历史输入

HTML是已有的本地生成器，不调用AI。固定文字、字号、背景、尺寸及位置后扫档；追加先用旧图作对照，不能一张手动位置、另一批恢复默认还称相同条件。

参考答案只在电脑，手机导入PNG原文件。替换已测输入前保留旧字节和SHA256，新输入不覆盖旧结果。原图参数、图库显示与助手实际接收画面不同；未抓取助手输入时，不把ADB截图当成其直接证明。
