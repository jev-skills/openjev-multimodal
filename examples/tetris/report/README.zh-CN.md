# 俄罗斯方块测试报告

[可视化报告](https://hand-in.github.io/openjev-multimodal/demos/tetris/report/) · [在浏览器中试玩](https://hand-in.github.io/openjev-multimodal/demos/tetris/web/) · [示例说明](../README.zh-CN.md) · [English](README.md)

三个本地模型通过 OpenJev Multimodal 各下了 10 局、每局 100 个方块：5 个随机种子 × 2 种提示方式，所有模型面对完全相同的方块序列。每次调用只问一个 Choice 问题，一次规划接下来的两个方块，只读取 1 个输出 token。下文的表格、图表、视频与网页回放全部由录制数据生成（测于 2026-09-21，Apple M3 Max）。

- **15 / 15** 视觉模式对局全部完成 10 次消除 (非法按键 0 · API 错误 0 · 兜底操作 0)
- **3 / 5** quality 对局达成目标时零空洞 (纯文字提示下为 4 / 5)
- **0.15 · 0.65 · 0.91 s** 每次决策耗时中位数 (fast · balanced · quality；每次调用规划两个方块)
- **15,156** 100 个方块后的最高分 (quality · 纯文字提示 · 种子 101)

## 观看三个模型对局

种子 101、视觉提示，从第一个方块播放到第 10 次消除。等待时间是每次调用实测的往返耗时；按键、下落与消除动画按固定节奏播放。

| [![fast · Qwen3.5-0.8B](videos/fast.jpg)](videos/fast.mp4)<br>**fast · Qwen3.5-0.8B**<br>56 个方块达成目标 · 20 个空洞 · 每次调用 0.14 秒 | [![balanced · Qwen3.5-4B](videos/balanced.jpg)](videos/balanced.mp4)<br>**balanced · Qwen3.5-4B**<br>30 个方块达成目标 · 2 个空洞 · 每次调用 0.51 秒 | [![quality · Qwen3.6-35B-A3B](videos/quality.jpg)](videos/quality.mp4)<br>**quality · Qwen3.6-35B-A3B**<br>32 个方块达成目标 · 1 个空洞 · 每次调用 0.92 秒 |
|---|---|---|

## 测试结论

- **三个模型全部达成目标。** 视觉模式的 15 局全部完成 10 次消除，没有非法按键、API 错误或兜底操作。quality 模型在 5 局中有 3 局达成目标时盘面没有任何空洞（纯文字提示下为 4 局）。
- **模型越大，判断越好。** 与参考评估器的一致率从 42%（0.8B）提升到 73%（4B）和 84%（35B-A3B），平均遗憾值从 1.87 降到 0.69 和 0.09。35B 混合专家模型每个 token 只激活约 3B 参数，单次决策 0.91 秒，仅为 4B 模型的 1.4 倍。
- **精确事实负责决策，图片负责解释。** 只给结果缩略图、不给文字事实时，三个模型在固定状态集上每次决策损失 2.4–2.6 分；只给文字事实，4B 与 35B 模型都降到 0.27；文字事实加结果缩略图让三个模型都达到各自最低：1.44、0.22、0.18。
- **模型越小，图片越重要。** 完整对局中，0.8B 模型有结果缩略图时平均消除 26.6 行，没有时只有 13.6 行；堆满出局也从 5 局减少到 1 局。对 4B 与 35B 模型，纯文字提示表现相当，每次调用还能快 142–360 毫秒。
- **先选对画面，再用尽量少且清晰的 token。** 结果缩略图放大 2 倍会多出约 150 个输入 token，决策并未更好；缩小一半影响不大。整张棋盘截图并不适合这个决策：对 4B 模型，它把遗憾值从 0.22 抬高到 0.67，调用中位数从 0.59 秒增加到 0.94 秒。
- **延迟由输入 token 决定。** 每次调用只输出 1 个 token。服务端耗时与往返耗时相差约 1 毫秒，代码侧规划耗时 25–35 毫秒；决定速度的是提示长度、图像 token 与模型规模。

## 100 个方块后的结果

| 档位 | 提示方式 | 完成 10 次消除 | 零空洞达成 | 堆满出局 | 达成所需方块 | 消除行数 | 得分（平均 / 最高） | 最多空洞 | 调用中位数 · p90 | 一致率 | 遗憾值 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fast · Qwen3.5-0.8B | 视觉 | 5 / 5 | 0 / 5 | 1 / 5 | 48 | 26.6 | 7,186 / 8,714 | 29 | 0.15 s · 0.18 s | 42% | 1.87 |
| fast · Qwen3.5-0.8B | 纯文字 | 4 / 5 | 0 / 5 | 5 / 5 | 54 | 13.6 | 3,199 / 5,410 | 28 | 0.08 s · 0.10 s | 28% | 2.35 |
| balanced · Qwen3.5-4B | 视觉 | 5 / 5 | 0 / 5 | 0 / 5 | 40 | 35.8 | 11,837 / 13,668 | 9 | 0.65 s · 0.89 s | 73% | 0.69 |
| balanced · Qwen3.5-4B | 纯文字 | 5 / 5 | 1 / 5 | 0 / 5 | 30 | 36.4 | 12,818 / 13,868 | 5 | 0.51 s · 0.64 s | 72% | 0.67 |
| quality · Qwen3.6-35B-A3B | 视觉 | 5 / 5 | 3 / 5 | 0 / 5 | 28 | 38.2 | 13,696 / 14,416 | 3 | 0.91 s · 1.13 s | 84% | 0.09 |
| quality · Qwen3.6-35B-A3B | 纯文字 | 5 / 5 | 4 / 5 | 0 / 5 | 34 | 38.2 | 14,384 / 15,156 | 3 | 0.55 s · 0.64 s | 82% | 0.25 |

每行 5 局（种子 101、202、303、404、505）。“达成所需方块”与“最多空洞”取各局中位数，消除行数取平均值。一致率与遗憾值把每个非强制决策与参考评估器（Yiyuan Lee 调优权重）比较；参考评估器从不参与落子。

## 图表

![视觉模式下每一次调用的往返耗时。白色短线为中位数，灰色短线为纯文字提示的中位数。](figures/latency.zh.svg)

*视觉模式下每一次调用的往返耗时。白色短线为中位数，灰色短线为纯文字提示的中位数。*

![100 个方块后的得分、消除行数与最多空洞；每个点代表一局。](figures/outcomes.zh.svg)

*100 个方块后的得分、消除行数与最多空洞；每个点代表一局。*

## 一次决策如何完成

1. **枚举。** 代码列出当前方块的所有合法落点（旋转、平移、硬降），再对每个落点列出下一个方块的所有落点，通常得到 300–600 个两步方案。
2. **无权重剪枝。** 只有当某个方案在每一项实测指标（消除行数、空洞、最高高度、总高度、凹凸度）上都不优于另一个方案时，才会被剔除。剪枝后中位数只剩 3 个方案，并按从左到右排列，顺序本身不提供任何暗示。
3. **只问一次。** 一个 Choice 问题把每个方案写成完整的按键序列并附上实测结果，同时用一张图片把每个方案的结果画成带字母的小图。
4. **读取 1 个 token。** OpenJev 返回全部选项标签上的完整概率分布，代码据此为两个方块依次按键。若剪枝后只剩一个方案，则不调用模型、直接执行，并记为强制决策（1,427 次决策中有 103 次）。

### 真实示例：quality 对局，种子 101，第 8 次决策

![发送的图片：576 × 128 像素，72 个图像 token。A 方案消除一行（+1）。](figures/example-sheet.png)

*发送的图片：576 × 128 像素，72 个图像 token。A 方案消除一行（+1）。*

**请求**

```json
{
  "model": "jev-latest",
  "state": {
    "game": "Tetris well: 10 columns (0-9, left to right) x 20 rows",
    "falling": "J",
    "next": [
      "S",
      "O",
      "I"
    ],
    "lines_cleared": 5
  },
  "questions": {
    "plan": {
      "type": "choice",
      "instructions": {
        "task": "Choose the plan to play: the keys for the falling piece, then for the next piece.",
        "goal": "Clear lines and keep the well healthy for the pieces that follow.",
        "priorities": [
          "Complete rows whenever possible; more rows at once is better.",
          "Do not cover empty cells: new holes are the most expensive mistake.",
          "Keep the stack low and its surface even, so the next pieces fit."
        ],
        "fields": {
          "cols": "columns the piece occupies after the drop",
          "clears": "rows completed by the two moves",
          "new holes": "empty cells the two moves seal under blocks",
          "height": "tallest column afterwards, in rows"
        },
        "image": "The image has one tile per option, lettered like the options: the well after both pieces land. +N marks rows cleared; dark gaps under blocks are holes."
      },
      "criteria": {
        "0": "J: left left left drop → cols 0-2; then S: drop → cols 3-5. Result: clears 1, new holes 0, height 1",
        "1": "J: left drop → cols 2-4; then S: rotate-back left left left drop → cols 0-1. Result: clears 0, new holes 1, height 3",
        "2": "J: rotate rotate right right right right drop → cols 7-9; then S: right drop → cols 4-6. Result: clears 0, new holes 3, height 3"
      }
    }
  },
  "images": [
    "data:image/png;base64,iVBORw0KGgoAAAANSU… (2 KB PNG)"
  ]
}
```

**响应（数值已取整）**

```json
{
  "model": "jev-latest",
  "answers": {
    "plan": {
      "type": "choice",
      "choice": "0",
      "probabilities": {
        "0": 0.8122,
        "1": 0.099,
        "2": 0.0887
      },
      "confidence": 0.4421
    }
  },
  "usage": {
    "input_tokens": 490,
    "output_tokens": 1
  }
}
```

Jev 把 81% 的概率给了方案 A：唯一既能消行又不产生新空洞的方案。本次调用耗时 0.93 秒，输入 490 个 token。

**图像分辨率。** Qwen 的视觉编码器把图片切成 16 像素的 patch，再把每 2 × 2 个 patch 合并成 1 个 token（32 像素）。结果缩略图让每个棋盘格恰好落在一个 16 像素 patch 上，每个方案只截取实际用到的行，所有小图都对齐 32 像素网格，因此服务端无需重新缩放（边长不超过 1,024 像素，图像 token 不超过 512）。

## 设计实验

正式测试前，同样的 48 个决策状态以 8 种方式分别呈现给每个模型。这些状态来自种子 1–4 上的参考对局；设计提示词时从未使用正式测试的种子。

![每种呈现方式的平均遗憾值（越低越好）与调用耗时中位数。](figures/design.zh.svg)

*每种呈现方式的平均遗憾值（越低越好）与调用耗时中位数。*

| 呈现方式 | 输入 token | 遗憾值 · fast | 遗憾值 · balanced | 遗憾值 · quality | 调用 · fast | 调用 · balanced | 调用 · quality |
|---|---|---|---|---|---|---|---|
| 文字事实 + 结果缩略图（默认） | 492 | 1.44 | 0.22 | 0.18 | 137 ms | 593 ms | 938 ms |
| 文字事实 + ½ 尺寸缩略图 | 438 | 1.18 | 0.30 | 0.06 | 111 ms | 439 ms | 587 ms |
| 文字事实 + 2 倍缩略图 | 642 | 1.38 | 0.35 | 0.17 | 162 ms | 647 ms | 864 ms |
| 仅文字事实，不发图片 | 374 | 1.58 | 0.27 | 0.27 | 90 ms | 428 ms | 566 ms |
| 文字事实 + 棋盘截图 | 696 | 2.39 | 0.67 | 0.24 | 199 ms | 936 ms | 1278 ms |
| 文字事实 + ½ 尺寸截图 | 480 | 1.69 | 0.52 | 0.22 | 128 ms | 675 ms | 907 ms |
| 文字事实 + 2 倍截图 | 888 | 1.77 | 0.68 | 0.27 | 272 ms | 1414 ms | 1645 ms |
| 仅结果缩略图，无文字事实 | 410 | 2.43 | 2.40 | 2.60 | 123 ms | 520 ms | 817 ms |

## 方法与来源

- **硬件。** Apple M3 Max，128 GB；llama.cpp b9670（Metal），单推理槽、4 个 CPU 线程、8,192 token 上下文、每张图 512 个图像 token 上限。各档位依次测试，同一时间只有一个档位在推理，也没有其他推理任务。
- **模型。** 使用 OpenJev 固定版本的三个档位：Qwen3.5-0.8B Q4_K_M、Qwen3.5-4B Q4_K_M 与 Qwen3.6-35B-A3B UD-Q4_K_XL，各自搭配对应的 F16 视觉投影器。权重文件均按 SHA-256 与固定的 Hugging Face 版本核对。
- **流程。** 种子 101、202、303、404、505；每局 100 个方块，或直到堆满出局；所有模型使用相同的种子、提示词与剪枝规则。目标按 10 次独立的消除事件计算。
- **记录内容。** 客户端往返耗时（本机）、服务端耗时（`x-openjev-elapsed-ms`）、输入 token、完整概率分布以及每一次按键。参考评估器只在事后为决策打分。
- **回放。** 视频与网页回放都按录制的按键重新模拟。Python 与 JavaScript 两套引擎逐一复现了全部 30 局、1,427 次决策以及每一个候选方案。
- **局限。** 每种配置只有 5 个种子，样本较小；遗憾值与一致率取决于所选参考评估器；耗时只代表这台 Mac 在无并发负载时的表现。方块在可见区域内生成，不支持暂存（hold），也不做软降塞入与旋转技巧。

## 复现

```bash
uv run openjev serve --profile balanced     # 一次只运行一个档位
uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,text
uv run python examples/tetris/play.py ablation
uv run python examples/tetris/report.py     # 汇总、图表、报告页面与回放数据
uv run python examples/tetris/video.py --profile balanced --seed 101
```

## 本目录文件

- `runs/*.json`：每局每次决策的完整记录（每行一次决策）。
- `ablation/*.json`：设计实验结果。
- `summary.json`：报告使用的汇总数据；`replays.json`：网页回放数据。
- `figures/`：SVG 图表与示例图片；`videos/`：三个档位的对局视频与封面。
