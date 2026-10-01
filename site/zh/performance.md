---
title: 延迟
description: OpenJev Multimodal 的请求时间花在哪里、改了什么：混合架构 Qwen 的共享前缀预填充、经核对的模板骨架与图片一次缩放，附优化前后实测。
---

# 延迟

**同一 state 的多个问题，最高提速 60%。判断结果不变。**

每个答案只输出一个 token，延迟几乎都来自提示处理：state、图片和每个问题。我们逐段计时，去掉了重复的工作。

![balanced 档位优化前后的请求延迟中位数](/performance.zh.svg)

<div class="latency">

**一个问题**

|  | fast <span class="model">0.8B</span> | balanced <span class="model">4B</span> | quality <span class="model">35B-A3B</span> |
| --- | ---: | ---: | ---: |
| 客服工单 | 70 ms <span class="delta">−13%</span> | 278 ms <span class="delta">−4%</span> | 332 ms <span class="delta">−6%</span> |
| 1.2k token 条款 | 205 ms <span class="delta">−7%</span> | 996 ms <span class="delta">−1%</span> | 1.09 s <span class="delta">−2%</span> |
| 448×672 截图 | 136 ms <span class="delta">−7%</span> | 735 ms <span class="delta">−1%</span> | 1.04 s <span class="delta">−3%</span> |
| 2048×1536 照片 | 256 ms <span class="delta">−18%</span> | 911 ms <span class="delta">−6%</span> | 1.42 s <span class="delta">−1%</span> |
| 重复请求 | 14 ms <span class="delta">−41%</span> | 35 ms <span class="delta">−20%</span> | 34 ms <span class="delta">−20%</span> |

**同一 state 的四个问题**

|  | fast <span class="model">0.8B</span> | balanced <span class="model">4B</span> | quality <span class="model">35B-A3B</span> |
| --- | ---: | ---: | ---: |
| 客服工单 | 165 ms <span class="delta">−35%</span> | 623 ms <span class="delta">−42%</span> | 859 ms <span class="delta">−35%</span> |
| 1.2k token 条款 | 311 ms <span class="delta">−41%</span> | 1.43 s <span class="delta">−45%</span> | 1.68 s <span class="delta">−39%</span> |
| 448×672 截图 | 235 ms <span class="delta">−53%</span> | 1.00 s <span class="delta">−60%</span> | 2.09 s <span class="delta">−57%</span> |

</div>

交替测量 7 次的中位数，客户端计时，百分比为相对上一版本的变化。[测量方法](#方法)

## 每个响应都带服务端耗时

```json
"timing": {
  "processing_ms": 131.4,
  "parse_ms": 0.9,
  "prepare_ms": 2.1,
  "queue_ms": 0.0,
  "inference_ms": 128.2
}
```

`processing_ms` 从收到请求计到响应就绪，各阶段之和等于它。`x-openjev-processing-ms` 与 `Server-Timing` 响应头携带相同数值，错误响应也有。`model`、`answers`、`usage` 保持 Jev 格式，官方 `typesafe-sdk` 会忽略这个额外字段；设置 `OPENJEV_RESPONSE_TIMING=false` 即可去掉。[字段说明](./api#响应与用量)

## 时间花在哪里

上一版本，balanced 档位：

| 阶段 | 开销 | 发生于 |
| --- | --- | --- |
| 聊天模板（`/apply-template`） | 9 毫秒，与内容长短无关 | 每个请求 |
| token 计数（`/tokenize`） | 150 token 0.6 毫秒，1,250 token 2.7 毫秒 | 每个问题，依次执行 |
| 共享 state 与图片 | 重新读取、重新编码 | 每多一个问题 |
| API 处理照片 | 2048×1536 需 65 毫秒，4032×3024 需 119 毫秒，随后 llama.cpp 再缩放一次 | 每张图片 |
| 提示处理 | 276 token 工单 0.29 秒，1.2k token 条款 1.0 秒，448×672 截图 0.75 秒 | 每个 token 与图片 |

Qwen3.5、Qwen3.6 与 Qwen3.8 都是混合架构，循环层无法回滚到任意位置，而 llama.cpp 只在每个提示末尾附近保存检查点，所以之后的每个问题都要重读整个 state：`forcing full prompt re-processing due to lack of cache data`。

## 改了什么

**共享前缀预填充。** 多问题请求先计算一次共享前缀，每个问题从该检查点继续，只读自己的问题文本。用量仍按每个问题的完整提示统计。

**模板骨架。** Qwen 模板在每条 user 或 system 消息两侧加上固定文本。API 只渲染一次这个框架，前几次结果与 llama.cpp 逐字核对，之后在本地填充，每个请求省去一次后端调用。含 assistant、tool 消息或两端有特殊空白的内容，仍由 llama.cpp 渲染。

**并行计数 token。** 共享前缀只计一次，各问题并行计数。

**图片只缩放一次。** 超出预算的图片直接缩放到视觉编码器使用的尺寸（32 像素网格），不再缩放两次。大尺寸 JPEG 以降采样方式解码：API 处理 2048×1536 降到 31 毫秒，4032×3024 降到 55 毫秒。

## 重复的 state

当连续请求重复同一个 state、只换问题时，API 会在 state 末尾保留检查点，每个请求只读取自己的问题。OpenJev 的 [llama.cpp 补丁](./models#max-qwen3-8-27b)更进一步：把检查点精确放在 state 末尾，并允许请求跳过 llama.cpp 为检查点每个提示末尾而额外进行的一次计算。

| Qwen3.8-27B，精简俄罗斯方块提示 | 每次决策中位数 |
| --- | ---: |
| 原版 llama.cpp | 1.93 秒 |
| 启用重复 state 缓存 | 0.83 秒 |
| 缓存 + 补丁 | 0.66 秒 |

每种配置 16 次决策，同一时间只运行一个服务（[测量记录](https://github.com/Hand-In/openjev-multimodal/tree/main/examples/tetris/report/probes)）。固定检查集的 32 个答案与原版 llama.cpp 完全一致。设置 `OPENJEV_PRIME_REPEATED_STATE=false` 可关闭该缓存。

多个 state 也可以轮流使用。`scripts/build-llama.sh` 构建的 llama.cpp 会把之前的提示连同检查点保存在内存中：在 Qwen3.5-4B 上轮流使用 4 个 800 token 的 state，每次回答 0.11 秒；llama.cpp b9670 每次都要重读 state，需 0.69 秒。

## 准确性

每次试验向两个版本发送完全相同的请求。

- **判断：** 168 对请求全部一致（3 个档位 × 8 类请求 × 7 次）。
- **单问题、无大图：** 概率完全相同。
- **多问题：** 0.8B 与 4B 模型的概率差不超过 0.001，35B-A3B 不超过 0.067。前缀改为单独一批计算，浮点求和顺序随之变化。
- **照片：** 不超过 0.018，因为只重采样一次。

## 下一步

- 从共享检查点批量计算同一请求的多个问题。
- 标签先验校准与多 token 选项打分；二者会改变概率，需要单独评估。
- 跨请求连续批处理，提升吞吐。
- 有了带标注的判断数据后，训练读数（如 LoRA，或从 quality 档位蒸馏）。

## 方法

`scripts/latency.py` 把每个新请求按轮换顺序发给两个版本。两个版本各自运行 llama.cpp 进程，互不共享缓存。每个 state 以新的标识开头，确保请求都是冷启动；重复请求用例只计第二次的耗时。每类请求预热两次后测 7 次，2026 年 9 月 21 日测于 M3 Max（128 GB）与 llama.cpp b9670，没有样本与其他推理重叠。

```bash
uv run python scripts/latency.py --quiet --output benchmarks/performance/balanced.json \
  before=http://127.0.0.1:8101 after=http://127.0.0.1:8100
uv run python scripts/render_performance.py --chart
```

测量记录：[fast](https://github.com/Hand-In/openjev-multimodal/blob/main/benchmarks/performance/fast.json) · [balanced](https://github.com/Hand-In/openjev-multimodal/blob/main/benchmarks/performance/balanced.json) · [quality](https://github.com/Hand-In/openjev-multimodal/blob/main/benchmarks/performance/quality.json)

<style scoped>
.delta { margin-left: 6px; font-size: 12px; color: var(--vp-c-text-3); white-space: nowrap; }
.model { margin-left: 4px; font-weight: 400; color: var(--vp-c-text-3); }
.latency td, .latency th { white-space: nowrap; }
td { font-variant-numeric: tabular-nums; }
</style>
