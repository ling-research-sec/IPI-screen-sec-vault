#!/usr/bin/env python3
"""Copy the current built APK and write its checksum. No logs or source bundles."""
from pathlib import Path
import hashlib
import shutil
import zipfile

root = Path(__file__).resolve().parents[1]
dist = root / 'dist'
dist.mkdir(exist_ok=True)
apk = dist / 'IPI-Surface-Lab-debug.apk'
shutil.copy2(root / 'app/build/outputs/apk/debug/app-debug.apk', apk)
with zipfile.ZipFile(apk) as archive:
    assert archive.testzip() is None
    assert archive.read('AndroidManifest.xml') and archive.read('classes.dex')
with apk.open('rb') as source:
    digest = hashlib.sha256(source.read()).hexdigest()
(dist / 'SHA256SUMS').write_text(f'{digest}  {apk.name}\n')
print(f'{apk.name}: {apk.stat().st_size} bytes; sha256={digest}')
