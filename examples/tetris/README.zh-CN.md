# 由 OpenJev Multimodal 来玩的俄罗斯方块

**一个完整的俄罗斯方块游戏，由本地模型通过 SystemOne API 来玩。** 规则交给代码：列出所有合法走法、测量结果、按下按键。判断交给 Jev：阅读简短的方案列表，看一眼标有字母的结果图，只用 1 个输出 token 选出方案。

[![Qwen3.5-4B 通过 OpenJev Multimodal 玩俄罗斯方块](report/videos/balanced.jpg)](report/videos/balanced.mp4)

[测试报告](report/README.zh-CN.md) · [可视化报告](https://hand-in.github.io/openjev-multimodal/demos/tetris/report/) · [在浏览器中试玩](https://hand-in.github.io/openjev-multimodal/demos/tetris/web/) · [English](README.md)

## 运行

```bash
uv run openjev serve                                  # balanced 档位，端口 8000
uv run python examples/tetris/play.py play --seed 7   # 在终端里逐步查看一局
uv run python examples/tetris/serve.py                # 浏览器游戏：http://127.0.0.1:8765
```

浏览器游戏有三种模式。**回放**按录制数据逐键重演对局，显示真实概率与耗时，也可以作为静态页面使用。**实时 Jev** 每一步都请求本机模型。**亲自玩**就是普通的俄罗斯方块：`←` `→` 移动，`↑` 或 `X` 旋转，`Z` 反向旋转，`↓` 软降，`Space` 硬降，`P` 暂停。

## 一次决策如何完成

每次调用同时决定**当前方块与下一个方块**，因此 100 个方块的一局最多只需 50 次调用。

1. **枚举。** `tetris.py` 列出当前方块通过旋转、平移、硬降能到达的所有落点，再为每个落点列出下一个方块的所有落点，通常得到 300–600 个方案。
2. **无权重剪枝。** 只有当一个方案在全部五项实测指标（消除行数、空洞、最高高度、总高度、凹凸度）上都不被其他方案持平或超越时才会保留。剪枝后中位数只剩 3 个方案，按从左到右排列，位置本身不提供暗示。若只剩一个方案，则不调用模型、直接执行。
3. **只问一次。** 每个方案成为一个 Choice 选项：两个方块的完整按键序列，加上实测结果。

   ```text
   J: left left left drop → cols 0-2; then S: drop → cols 3-5. Result: clears 1, new holes 0, height 1
   ```

   instructions 说明目标与优先级（尽量消行、不封住空格、保持堆叠低而平整），并逐项解释字段含义。游戏状态以 JSON 发送：当前方块、接下来三个方块、已消除行数。
4. **展示结果。** 一张图片把每个方案执行后的棋盘画成带字母的小图，`+N` 表示消除的行数，空洞以深色空格显示。
5. **读取 1 个 token。** 返回值是全部方案标签上的完整概率分布。`play.py` 按选中的方案按键，并检查每个按键都真正生效；不存在兜底操作。

### 图像分辨率

Qwen 的视觉编码器把图片切成 16 像素的 patch，再把每 2 × 2 个 patch 合并成 1 个 token（32 像素）。结果缩略图让每个棋盘格恰好落在一个 16 像素 patch 上，每个方案只截取实际用到的行，所有小图对齐 32 像素网格：三个方案的缩略图为 576 × 128 像素，只占 72 个图像 token，服务端无需重新缩放。

[设计实验](report/README.zh-CN.md#设计实验)在同样的 48 个状态上比较了 8 种呈现方式。决定结果的是精确的文字事实：对任何模型，只给图片都不够；在文字事实之外加上结果缩略图，三个模型的遗憾值都最低；整张棋盘截图则更慢也更差。对 4B 与 35B 模型，纯文字提示是更快且同样可靠的选择（`--mode text`）。

## 结果

每个档位 5 个种子 × 100 个方块，视觉提示。完整数据、图表与视频见[测试报告](report/README.zh-CN.md)。

| 档位 | 模型 | 完成 10 次消除 | 达成时零空洞 | 平均消除行数 | 最高分 | 调用中位数 |
| --- | --- | --- | --- | --- | --- | --- |
| `fast` | Qwen3.5-0.8B | 5 / 5 | 0 / 5 | 26.6 | 8,714 | 0.15 秒 |
| `balanced` | Qwen3.5-4B | 5 / 5 | 0 / 5 | 35.8 | 13,668 | 0.65 秒 |
| `quality` | Qwen3.6-35B-A3B | 5 / 5 | 3 / 5 | 38.2 | 14,416 | 0.91 秒 |

## 复现测试

一次只运行一个档位，然后根据录制数据重建报告。只有前两条命令会执行推理。

```bash
uv run openjev serve --profile balanced
uv run python examples/tetris/play.py bench --seeds 101,202,303,404,505 --modes vision,text
uv run python examples/tetris/play.py ablation
uv run python examples/tetris/report.py
uv run python examples/tetris/video.py --profile balanced --seed 101   # 需要 ffmpeg
```

`bench` 把每一次决策写入 `report/runs/<档位>.json`；`report.py` 重新生成汇总、图表、报告页面与回放数据。

## 文件

| 文件 | 作用 |
| --- | --- |
| `tetris.py` | 游戏引擎：SRS 旋转、带种子的 7-bag、落点枚举、两步方案、占优剪枝 |
| `vision.py` | 发给 Jev 的图片：结果缩略图，以及设计实验中使用的整盘截图 |
| `jev.py` | 提示词、请求构造与精简的 OpenJev 客户端 |
| `play.py` | `play`、`bench`、`ablation` 三个命令 |
| `replay.py` | 按录制数据重新模拟对局，并与录制结果逐项核对 |
| `video.py` | 渲染回放视频（H.264，1280 × 720） |
| `report.py`、`pages.py` | 汇总数据、图表与报告页面 |
| `serve.py`、`web/` | 浏览器游戏：回放、实时 Jev、亲自玩；`web/tetris.js` 与 `tetris.py` 完全一致 |
| `report/` | 录制数据、设计实验、图表、视频与测试报告 |
