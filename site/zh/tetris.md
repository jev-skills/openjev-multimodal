---
title: 俄罗斯方块演示 —— 本地模型通过 OpenJev 对局
description: 三个 Qwen 模型通过兼容 Jev 的 OpenJev Multimodal API 玩俄罗斯方块，每两个方块只需 1 个输出 token。包含对局视频、延迟、结果与图像分辨率设计实验。
---

# 由本地模型来玩的俄罗斯方块

一个完整的俄罗斯方块游戏，由 Qwen 模型通过 `POST /v1/systemone` 来玩。规则交给代码：列出所有合法走法、测量结果、按下按键。判断交给 OpenJev：阅读简短的方案列表，看一眼标有字母的结果图，**每两个方块只用 1 个输出 token** 选出方案。

**[在浏览器中试玩 →](https://hand-in.github.io/openjev-multimodal/demos/tetris/web/)** &nbsp; [完整测试报告](https://hand-in.github.io/openjev-multimodal/demos/tetris/report/) · [源码与录制数据](https://github.com/Hand-In/openjev-multimodal/tree/main/examples/tetris)

| 结果 | 实测 |
| --- | --- |
| 完成 10 次消除的对局（视觉提示） | **15 / 15**，无非法按键、API 错误或兜底操作 |
| quality 达成目标时零空洞 | **3 / 5**（纯文字提示下为 4 / 5） |
| 每次决策耗时中位数（fast · balanced · quality） | **0.15 · 0.65 · 0.91 秒** |
| 100 个方块后的最高分 | **15,156**（quality、纯文字提示、种子 101） |

## 观看三个模型对局

种子 101、视觉提示，从第一个方块播放到第 10 次消除。等待时间是每次调用实测的往返耗时；按键、下落与消除动画按固定节奏播放。

<div class="tetris-videos">
<figure>
<video src="../../examples/tetris/report/videos/fast.mp4" poster="../../examples/tetris/report/videos/fast.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>fast · Qwen3.5-0.8B</strong>56 个方块达成目标 · 20 个空洞 · 每次调用 0.14 秒</figcaption>
</figure>
<figure>
<video src="../../examples/tetris/report/videos/balanced.mp4" poster="../../examples/tetris/report/videos/balanced.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>balanced · Qwen3.5-4B</strong>30 个方块达成目标 · 2 个空洞 · 每次调用 0.51 秒</figcaption>
</figure>
<figure>
<video src="../../examples/tetris/report/videos/quality.mp4" poster="../../examples/tetris/report/videos/quality.jpg" controls muted playsinline preload="none"></video>
<figcaption><strong>quality · Qwen3.6-35B-A3B</strong>32 个方块达成目标 · 1 个空洞 · 每次调用 0.92 秒</figcaption>
</figure>
</div>

## 一次决策如何完成

1. **枚举。** 代码列出当前方块的所有落点（旋转、平移、硬降），再为每个落点列出下一个方块的所有落点，通常得到 300–600 个两步方案。
2. **无权重剪枝。** 只有当某个方案在每一项实测指标（消除行数、空洞、最高高度、总高度、凹凸度）上都不优于另一个方案时才会被剔除。剪枝后中位数只剩 3 个方案，按从左到右排列，顺序本身不提供暗示。
3. **只问一次。** 一个 Choice 问题把每个方案写成完整的按键序列并附上实测结果，同时用一张图片把每个方案的结果画成带字母的小图。
4. **读取 1 个 token。** 返回值是全部方案标签上的完整概率分布，代码据此为两个方块依次按键。若剪枝后只剩一个方案，则不调用模型、直接执行。

```text
J: left left left drop → cols 0-2; then S: drop → cols 3-5. Result: clears 1, new holes 0, height 1
```

![一次真实决策发送的图片：三个带字母的结果小图，A 方案消除一行](../../examples/tetris/report/figures/example-sheet.png)

在这次真实决策中，quality 模型把 81% 的概率给了 A：唯一既能消行又不产生新空洞的方案。本次调用耗时 0.93 秒，输入 490 个 token。

**图像分辨率。** Qwen 的视觉编码器把图片切成 16 像素的 patch，再把每 2 × 2 个 patch 合并成 1 个 token（32 像素）。结果缩略图让每个棋盘格恰好落在一个 16 像素 patch 上，每个方案只截取实际用到的行，所有小图对齐 32 像素网格：三个方案的缩略图为 576 × 128 像素，只占 72 个图像 token，服务端无需重新缩放。

## 100 个方块后的结果

每行 5 局（种子 101、202、303、404、505），所有模型面对相同的方块序列。

| 档位 | 提示方式 | 完成 10 次消除 | 零空洞达成 | 堆满出局 | 平均消除行数 | 得分（平均 / 最高） | 调用中位数 · p90 | 一致率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fast · 0.8B | 视觉 | 5 / 5 | 0 / 5 | 1 / 5 | 26.6 | 7,186 / 8,714 | 0.15 · 0.18 秒 | 42% |
| fast · 0.8B | 纯文字 | 4 / 5 | 0 / 5 | 5 / 5 | 13.6 | 3,199 / 5,410 | 0.08 · 0.10 秒 | 28% |
| balanced · 4B | 视觉 | 5 / 5 | 0 / 5 | 0 / 5 | 35.8 | 11,837 / 13,668 | 0.65 · 0.89 秒 | 73% |
| balanced · 4B | 纯文字 | 5 / 5 | 1 / 5 | 0 / 5 | 36.4 | 12,818 / 13,868 | 0.51 · 0.64 秒 | 72% |
| quality · 35B-A3B | 视觉 | 5 / 5 | 3 / 5 | 0 / 5 | 38.2 | 13,696 / 14,416 | 0.91 · 1.13 秒 | 84% |
| quality · 35B-A3B | 纯文字 | 5 / 5 | 4 / 5 | 0 / 5 | 38.2 | 14,384 / 15,156 | 0.55 · 0.64 秒 | 82% |

一致率把每个非强制决策与参考评估器（Yiyuan Lee 调优权重）比较；参考评估器从不参与落子。

![各档位每一次调用的往返耗时与中位数](../../examples/tetris/report/figures/latency.zh.svg)

![100 个方块后的得分、消除行数与最多空洞，每个点代表一局](../../examples/tetris/report/figures/outcomes.zh.svg)

## 测试结论

- **三个模型全部达成目标。** 视觉模式的对局全部完成 10 次消除；quality 模型在 5 局中有 3 局达成目标时盘面零空洞。
- **模型越大，判断越好。** 与参考评估器的一致率从 42%（0.8B）提升到 73%（4B）和 84%（35B-A3B）。35B 混合专家模型每个 token 只激活约 3B 参数，单次决策 0.91 秒，仅为 4B 模型的 1.4 倍。
- **精确事实负责决策，图片负责解释。** 只给结果图片时，所有模型的选择都明显变差；文字事实加结果缩略图让每个模型在下方的设计实验中都达到最低遗憾值。
- **模型越小，图片越重要。** 0.8B 模型有结果缩略图时平均消除 26.6 行，没有时只有 13.6 行。对 4B 与 35B 模型，纯文字提示表现相当，每次调用还能快 142–360 毫秒。
- **先选对画面，再用尽量少且清晰的 token。** 缩略图放大 2 倍会多出约 150 个输入 token，决策并未更好；整张棋盘截图让 4B 模型更慢，也更差。

![设计实验：同样 48 个决策状态的 8 种呈现方式的平均遗憾值与调用耗时中位数](../../examples/tetris/report/figures/design.zh.svg)

## 自己运行

```bash
uv run openjev serve                                  # balanced 档位，端口 8000
uv run python examples/tetris/serve.py                # 浏览器游戏：http://127.0.0.1:8765
uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505
```

浏览器游戏可以逐键回放每一局录制对局，也可以让本机模型实时对局，或者由你亲自来玩。回放使用与测试完全相同的引擎（Python 与 JavaScript 两套实现逐一核对）重新模拟录制的按键。实测环境为 Apple M3 Max 与 llama.cpp b9670；每种配置只有 5 个种子，样本较小，耗时取决于机器与负载。

<style scoped>
.tetris-videos { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 20px 0 8px; }
.tetris-videos figure { margin: 0; border: 1px solid var(--vp-c-divider); border-radius: 10px; overflow: hidden; background: var(--vp-c-bg-soft); }
.tetris-videos video { display: block; width: 100%; aspect-ratio: 16 / 9; background: #101713; }
.tetris-videos figcaption { padding: 10px 12px 12px; font-size: 13px; line-height: 1.5; color: var(--vp-c-text-2); }
.tetris-videos figcaption strong { display: block; color: var(--vp-c-text-1); }
@media (max-width: 760px) { .tetris-videos { grid-template-columns: 1fr; } }
</style>
