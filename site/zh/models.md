---
title: Qwen 模型选择与 Apple Silicon 性能
description: 对比本地 Qwen3.5 0.8B、4B、Qwen3.6 35B-A3B 与 Qwen3.8 27B 的使用定位，了解 Mac 实测延迟与资源取舍。
---

# 模型与性能

四个档位使用同一 API，权重与视觉投影器均固定版本。

| 档位 | 模型 | 量化 | 使用定位 |
| --- | --- | --- | --- |
| `fast` | Qwen3.5-0.8B | Q4_K_M | 低内存占用、简单判断 |
| `balanced`，默认 | Qwen3.5-4B | Q4_K_M | 日常文字与图片任务 |
| `quality` | Qwen3.6-35B-A3B | UD-Q4_K_XL | 大内存 Mac 上更强的知识与判断 |
| `max` | Qwen3.8-27B | UD-Q4_K_XL | Qwen 最强的本地模型 |

16 GB 或更大内存的 Mac 可从 balanced 开始，更小的内存预算可选 fast。quality 权重约 23.3 GB，max 约 17.6 GB，另需 0.9 GB 投影器。**实际验证机器是 M3 Max、128 GB 内存、40 核 GPU，未测量其他机器的最低内存要求。**

## max：Qwen3.8-27B

Qwen3.8-27B 是稠密模型：每个提示 token 都要经过全部 270 亿参数，在 M3 Max 上约 5 毫秒一个 token。[俄罗斯方块演示](./tetris)中一次完整的 305 token 决策需 1.9 秒；若连续请求的 state 相同，API 会缓存它，只读取新的问题：0.7 秒。

要达到这个速度，请用 OpenJev 补丁构建一次 llama.cpp，之后 `openjev serve` 会自动使用它：

```bash
scripts/build-llama.sh
uv run openjev serve --profile max
```

原版 llama.cpp 同样可以运行该档位，只是每个命中缓存的请求慢约 0.2 秒。`--quant Q8_0` 加载 8-bit 权重（29 GB）：在 M3 Max 上处理短提示比 UD-Q4_K_XL 快约 5%，固定检查集的 32 个答案全部一致。MTP 与推测解码在这里没有帮助：OpenJev 只读取一个输出 token。

## 实测结果

公开的 [180 题抽样](./benchmarks) 使用 Qwen3.6-35B-A3B UD-Q4_K_XL、llama.cpp b9670、单槽位、8,192 token 上下文和 Metal。该文字任务集合的 HTTP 延迟中位数为 **281 ms**，只代表这一组输入。[延迟 →](./performance)

长输入、多图片、更高图片 token 预算、并发、冷启动及其他 GPU 工作都会影响耗时。请求延迟不包含下载和模型加载。

## 单 token 的意义

每个问题只进行预填充和首 token 概率读数，无需生成推理文本或逐字输出 JSON。API 用真实概率构造类型化响应。

模型仍需读取完整 state。各问题在单槽位上依次执行。混合架构的循环层无法回滚到任意缓存位置，因此 API 只计算一次共享的 state，每个问题从检查点继续，只处理自己的文本。`x-openjev-cached-tokens` 显示复用的 token 数，响应中的 `timing` 对象显示耗时分布。

## 来源

确切版本见 [profiles.py](https://github.com/jev-skills/openjev-multimodal/blob/main/src/openjev/profiles.py)。

- 原始模型：[Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-4B)、[Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)、[Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B)。
- fast、balanced 与 max 的权重和投影器：Unsloth GGUF [0.8B](https://huggingface.co/unsloth/Qwen3.5-0.8B-GGUF)、[4B](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF)、[27B](https://huggingface.co/unsloth/Qwen3.8-27B-GGUF)。
- quality 权重：[Qwen3.6 MTP GGUF](https://huggingface.co/havenoammo/Qwen3.6-35B-A3B-MTP-GGUF)，配套投影器来自 [Unsloth](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF)。

本仓库原创代码采用 MIT 许可，模型权重与数据集保留各自许可。
