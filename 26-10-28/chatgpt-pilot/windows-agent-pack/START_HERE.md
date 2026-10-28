# Windows Agent：ChatGPT Advanced 原生共享识读 Pilot

## 直接执行的任务
你是 Android 自动化与实验工程师。请把本目录作为现有实验的可移植资源包，先只读检查这台 Windows 的模拟器，再实现并验证非 Root 采集。不要假定已有完整采集器。本包的 verify.py 只做离线资源校验，reference_scoring.py 只是原评分函数，不是自动化运行器。

先运行 `py -3 verify.py`。已有工程优先复用其展示和控制接口；没有工程时直接使用本包资源，不要求访问原 Mac。所有路径以本文件所在目录为根，用 pathlib 解析 manifest 内的相对路径；不要写死盘符、设备序列号、包名坐标或 Mac 路径。

## 先查环境，不换实验入口
1. 列出 adb devices -l、模拟器产品与版本、Android/API、分辨率、ABI、已运行实验及占用。所有 ADB 命令绑定明确 serial；不要停止别人的模拟器、ADB server 或实验。
2. “Windows 有模拟器”不等于“有 Google Android Emulator”。核实是否为 Android Studio/SDK 的 Android Emulator，以及是否真的提供 EmulatorController gRPC。雷电、BlueStacks、MuMu 等产品不得因支持 ADB 就假定支持此接口。若没有所需接口，报告阻断并等待用户选择，不安装另一套大型环境、不改系统、不自动改用外放。
3. 检查 ChatGPT 安装、登录、账号可用 Advanced、原生 Share Screen、后台对话及单 App 共享；登录交给用户。模型后端未确认就记录 unknown。只操作专用/空闲实例；启动与配置变化须明确 --execute，不覆盖已有 AVD。不要复用 Mac 的设备配置推断 Windows 能力。
4. 分开验证语音会话和 MediaProjection 状态。蓝色语音圆球、通知或按钮存在，均不单独证明共享有效；共享活动也不单独证明服务端已消费图像。确认共享任务属于图库/展示 App，而非整屏或 ChatGPT 自身。

## 必须保持的实验资源
- Advanced，禁止切换 Live/Standard；只用原生 Share Screen，只共享图库/原有展示 App。
- images 内8张图片为已有原PNG，不改内容、灰度、字号、位置、尺寸，不缩放、不增强、不重新随机字符串或生成图片。
- 固定100个大写字母，20×5，48px，1080×2400，黑底 RGB(0,0,0)，文字 RGB(g,g,g)。Ground Truth 仅留在电脑，不进手机标题、可访问性描述、通知或模型上下文。
- 执行顺序已经用种子20261028生成并固化在 pilot_manifest.json；不要再洗牌，图片每张至多一次。
- prompt.txt 是唯一提示词源；字节和换行保持不变。复用现成 prompt.wav，不重新TTS、不添加 Continue、不简化、不加入答案。
- prompt.wav 是24kHz/16-bit PCM/Mono、约23.8秒；文件检验通过，但 UNK/UNREADABLE 发音尚未人工听检。先让用户用耳机检查，避免外放触发被测App。语音不是字节级文字输入。
- 不上传测试图片、不调用 ChatGPT API、不换其他视觉入口；不 Root、Magisk、LSPosed、Frida 或修改 APK；不外放。

## gRPC 注音实现
使用 Google 官方 Python 客户端/官方 protobuf 接口 EmulatorController.injectAudio。先核对当前模拟器随附 proto、官方客户端来源和安装方式，不假设 aemu-grpc 已发布到 PyPI（原 Mac 对该 PyPI 名称查询返回404）。缺依赖时使用项目级隔离环境；若需从官方源码构建，固定版本并保留来源，别下载来源不明的同名包。

发现并绑定目标模拟器的 gRPC 地址、端口和认证信息；不要 get_default_emulator 后盲选第一台。保留本地认证，使用当前版本支持的 token/JWT，禁止输出凭据、密钥或完整 discovery 文件；控制服务仅本机访问。ADB console token 与 gRPC token/JWT 是不同概念。

按官方接口设置 AudioFormat（AUD_FMT_S16、Mono、samplingRate=24000），分块发送实际PCM数据，按样本数控制发送节奏，正确结束流，检查 RPC 终态、超时、取消、缓冲和麦克风占用错误。样例 get_default_emulator 是示例用法，不是多设备选择策略。模式/时序以当前 proto 为准，不照搬未验证参数。

分别验证：普通录音环境、Advanced前台、Advanced后台共享图库。gRPC成功只代表调用成功；普通录音必须确实录到注入声音，ChatGPT必须有可匹配的实际接收/原生回复证据。禁止拿另一个LLM转写GPT回答当原始结果。输出声音也必须避免物理外放；关闭宿主音频输出的方法要验证不同时禁用虚拟音频管线，不能直接假设 -no-audio 与注音兼容。

如果 Advanced 在该模拟器上不运行、登录受阻、后台共享失效或 gRPC 不支持，就记录具体阻断；不要替换视觉路径，不绕过功能限制。未经实际验证的功能写未验证。

## 分阶段与总量
A. 只读环境检查与离线资源校验。
B. 普通录音、Advanced前台和后台共享的音频能力验证。
C. 至少一个完整的展示→完整注音→结束判定→原生结果提取闭环。
D. A–C通过后，最多8轮连续会话 Pilot。

默认 Dry Run；真实操作入口必须显式 --execute。为避免隐形加测，本次给 ChatGPT 的注音请求总数也限8，能力探测记清用途与次数，普通录音器验证不算ChatGPT请求。优先把第一条有效识读同时用作单轮闭环里程碑，后续沿既定顺序继续；未执行的样本标记未执行。任何已发送但状态未知的请求都占用计数，不自动重发。需要额外能力探测或新会话时先报告，不越过8次预算。

一个正式 Advanced 聊天连续采集，8轮不重新建聊天、不修改研究设计。每轮固定完整录音一次。仅用于 continuous_session_pilot：随机顺序不消除上下文污染，不并入独立会话准确率统计。能力探测若使用另外的诊断聊天，明确区分它和正式 session，并同样计入总请求预算。

## 状态机与停止条件
INIT → VERIFY_DEVICE → VERIFY_GRPC_AUDIO → OPEN_CHATGPT_ADVANCED → START_APP_SCREEN_SHARE → VERIFY_GALLERY_SHARED → DISPLAY_IMAGE → INJECT_FIXED_WAV → WAIT_FOR_RESPONSE_COMPLETE → SAVE_TRIAL_STATE → NEXT_IMAGE → END_VOICE → EXPORT_NATIVE_TRANSCRIPT → VALIDATE_RESULTS → DONE。

- 图库先回到空白状态再开共享，避免初始化时泄漏前一个样本；不生成/改写正式样本。每张图展示后保持到回答结束。按原图核对目标区域与尺寸，不让图库控件遮挡或缩放图像。
- 回答完成优先用可验证的UI终态、文本稳定性及音频输出状态组合判断；VAD/静音只能辅助，不能固定等待后切图，也不能以出现100个字母作为结束条件。
- 不为看字幕在回答期间切走图库。可访问性树若只含前台App，就不能假定能读到后台ChatGPT。需要切前台的诊断与正式条件分开记录。
- 第一次全链路验证应确认长回复完整提取和可靠轮次匹配。若要结束会话才能确认完整性，不能把该问题藏起来继续8轮；先解决后台完成判据，否则停在单轮里程碑。
- 任意共享中断、提示未注完整、无回答、归属不明、完成不明、网络错误或额度耗尽，保存现场并停止；不跳错续跑、不为读对而重试。
- debug可以支持人工确认，但如依赖人工则明确标记，不能宣称全自动。

## 原生采集与记录
结束后通过原生复制或可靠UI文本提取完整会话，保存 full_transcript_raw.txt。不要把截断UI节点或拼接的屏幕自动折行当成完整原文；必要时保留原UI XML作为证据。只有轮次对应可靠才拆分每轮原文。不要取最后一句礼貌结束语冒充读图回答。

保留所有 First line、多余解释、空格换行、错误字符、[UNK]和[UNREADABLE]，不纠错、不补全、不删除说明或截取100字母。采集原文与评分分离。reference_scoring.py保留历史空白忽略字符指标；它的 exact_transcription 会忽略首尾CR/LF，不可冒充严格字节相等；需要严格格式指标时另算原始字符串相等，不覆盖原文。

每轮：session_id（本地ID与App会话身份分开）、trial_id、trial_index、grayscale、random_seed、image_path、image_sha256、ground_truth_sha256、prompt_audio_sha256、audio_injection_start/end、可靠时的response_start/end、voice_active、screen_share_active、raw_response、transcript_source、status、error_reason。缺失时间/答案写null，不补造。

[UNREADABLE]和读错是有效输出；音频/共享/提取失败是采集异常，不能记为[UNREADABLE]或0分。保存必要截图与JSONL事件日志；不要另开可能抢占MediaProjection的录屏App。保护已有结果，未完成状态不盲目重发。

## 最小交付
在本目录新增一个可重复运行的Python入口，复用本包资源；真实运行后保存原生对话、实际试次记录、必要截图和日志。只写一份简短 VALIDATION.md：真正通过/失败/未验证、人工介入、精确运行命令与结果、下一步。未发生采集时不创建假回复或空白“成功记录”。不要堆叠校验报告、回滚文档或重复音频副本。

## 已知历史（不是 Windows 测试结果）
Mac真机上曾看到ChatGPT原生共享图库，语音请求“全部读出来”后出现五行字母及复制按钮；这不是固定英文Prompt测试，也未核实准确率。某些界面曾出现输入框和文件菜单，但只验证到控件存在/键盘弹出，没有证明共享期间文字/音频附件能够完成任务。因此本任务不依赖打字或上传音频附件。

Mac还观察到语音界面存在但 MediaProjection=null：再次说明语音与共享状态要分开监测。模拟器 gRPC 注音、Advanced模拟器兼容性、自动结束判据和8轮采集均未验证；没有原生Pilot对话可迁移。不要把历史演示写成 Windows PASS。

## 官方入口（按 Windows 本机版本核验）
- https://developer.android.com/studio/run/emulator-console （这是console文档，不等于gRPC客户端文档）
- https://android.googlesource.com/platform/external/qemu/+/08aefd1f57c653d17e9ef972df9d82c978f7695c/android/android-grpc/python/samples/audio/inject_audio.py
- https://android.googlesource.com/platform/external/qemu/+/refs/heads/emu-master-dev/android/android-grpc/python/aemu-grpc/README.md
- https://android.googlesource.com/platform/external/qemu/+/refs/heads/emu-master-dev/android/android-grpc/docs/README.md
- https://help.openai.com/en/articles/20001274-chatgpt-voice
