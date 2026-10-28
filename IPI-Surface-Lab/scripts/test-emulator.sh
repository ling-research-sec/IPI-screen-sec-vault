#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
SERIAL=${ANDROID_SERIAL:-emulator-5580}
case "$SERIAL" in emulator-*) ;; *) echo 'ERROR: tests require a disposable emulator'; exit 2;; esac
[ "$(adb -s "$SERIAL" shell getprop ro.kernel.qemu | tr -d '\r')" = 1 ] || { echo 'ERROR: not an emulator'; exit 2; }
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest
adb -s "$SERIAL" install -r app/build/outputs/apk/debug/app-debug.apk
adb -s "$SERIAL" install -r app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
OUT=$(mktemp)
trap 'rm -f "$OUT"' EXIT
adb -s "$SERIAL" shell am instrument -w lab.ipi.surface.test/androidx.test.runner.AndroidJUnitRunner > "$OUT" 2>&1
cat "$OUT"
grep -Eq '^OK \([0-9]+ tests?\)' "$OUT"
