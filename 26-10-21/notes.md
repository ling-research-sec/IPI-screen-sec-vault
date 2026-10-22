# 1. 确认设备连接
adb devices -l

adb shell settings get secure assistant # 查询当前助手组件

# 2. 打开目标测试页面，选择小助手应用

"$ADB" -s "$SERIAL" shell am start -a android.settings.**VOICE_INPUT_SETTINGS**

# 3. 触发系统助手
adb shell am start -a android.intent.action.ASSIST


拉取最新一张图片的命令：

LATEST=$(adb shell "content query --uri content://media/external/images/media --projection _data --sort 'date_added DESC'" | tr -d '\r' | sed -n '1s/^Row: 0 _data=//p')
[ -n "$LATEST" ] && adb pull "$LATEST" "$HOME/Downloads/"
