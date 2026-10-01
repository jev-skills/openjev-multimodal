---
title: Qwen 模型选择与 Apple Silicon 性能
description: 对比本地 Qwen3.5 0.8B、4B 与 Qwen3.6 35B-A3B 的使用定位，了解 Mac 实测延迟与资源取舍。
---

# 模型与性能

三个档位使用同一 API，权重与视觉投影器均固定版本。

| 档位 | 模型 | 量化 | 使用定位 |
| --- | --- | --- | --- |
| `fast` | Qwen3.5-0.8B | Q4_K_M | 低内存占用、简单判断 |
| `balanced`，默认 | Qwen3.5-4B | Q4_K_M | 日常文字与图片任务 |
| `quality` | Qwen3.6-35B-A3B | UD-Q4_K_XL | 大内存 Mac 上更强的知识与判断 |

35B 模型为 MoE，每次约激活 3B 参数，但全部权重仍要占用内存。quality 权重约 23.3 GB，投影器约 0.9 GB。该检查点中的 MTP 张量没有用于推测解码，因为这里只读取第一个输出 token。

16 GB 或更大内存的 Mac 可从 balanced 开始，更小的内存预算可选 fast。quality 需要在权重之外预留充分空间。**实际验证机器是 M3 Max、128 GB 内存、40 核 GPU，未测量其他机器的最低内存要求。**

## 实测结果

公开的 [180 题抽样](./benchmarks) 使用 Qwen3.6-35B-A3B UD-Q4_K_XL、llama.cpp b9670、单槽位、8,192 token 上下文和 Metal。该文字任务集合的 HTTP 延迟中位数为 **281 ms**，不是所有输入的通用速度保证。

fast 和 quality 都已完成真实图片判断；balanced 已下载并达到多模态就绪状态。为控制本机负载，没有开展大量跨模型评测。

长输入、多图片、更高图片 token 预算、并发、冷启动及其他 GPU 工作都会影响耗时。请求延迟不包含下载和模型加载。

## 单 token 的意义

每个问题只进行预填充和首 token 概率读数，无需生成推理文本或逐字输出 JSON。API 用真实概率构造类型化响应。

模型仍需读取输入。各问题在单槽位上串行执行。混合架构的循环层无法回滚到任意缓存位置，因此多问题请求会先对共享前缀评估一次；之后每个问题从后端检查点继续，只处理自己的问题文本。`x-openjev-cached-tokens` 显示复用的 token 数，响应中的 `timing` 对象显示耗时分布。

## 来源

确切版本见 [profiles.py](https://github.com/Hand-In/openjev-multimodal/blob/main/src/openjev/profiles.py)。

- 原始模型：[Qwen3.5](https://huggingface.co/Qwen/Qwen3.5-4B)、[Qwen3.6-35B-A3B](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)。
- balanced 权重与投影器：[Unsloth GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF)。
- quality 权重：[Qwen3.6 MTP GGUF](https://huggingface.co/havenoammo/Qwen3.6-35B-A3B-MTP-GGUF)，配套投影器来自 [Unsloth](https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF)。

仓库原创代码使用 MIT 许可，模型和数据集遵循各自许可。
