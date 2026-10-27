准备了32张测试图片，覆盖g1–g32，每张图包含100个大写字母，20×5排列；原图48px、纯黑背景。

## 随机大写字母：
```
WEATFMVQYHCLIUIBZCDZ
PQLCFFGRQAXXLGTIRTGK
FTWUUWEIJQKUMAOUKARP
HPAHTEXPURNKYQYHOSZH
OWECDAHTVWPPSYPQNNAL
```

## 统一提示词：

```text
Please transcribe every character shown in the black test image currently displayed on my screen.

Preserve the exact character order and line breaks, including letters and special symbols. Do not translate, summarize, correct, or infer missing characters.

If a character cannot be identified, use [UNK]. If no characters can be read, output [UNREADABLE].

Output only the transcription.
```

## Perplexity助手模型

未知，设置模型的时候，只提示说是自动选择最优模型，没有具体说明是哪个模型。

## 实验pipeline

打开图片 -> 隐藏图库控件 -> 唤醒默认Perplexity助手 -> 发送统一提示词 -> 等待助手回复 -> 正式回复后操作adb截图保存

## 数据处理

借助codex进行了数据统计处理，我已抽样过20张，完全对的上数据。

目前已经复跑了三轮实验。若要测到满分识别率，需要继续扩充实验，目前预计在47-48左右，会到达满分区间。