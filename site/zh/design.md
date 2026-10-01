---
title: 概率读数原理与 Jev 兼容性
description: 了解完整单 token 候选概率的计算方式、SystemOne 兼容边界，以及与其他 OpenJev 实现的区别。
---

# 原理与兼容性

这是 Jev 风格 SystemOne 接口的独立实现，并扩展了本地图片输入。项目与 TypeSafe 无隶属关系，也不包含其专有 Jev 权重。

## 接口兼容

请求结构、Noul/Choice/Score 类型、命名响应与概率字段遵循公开接口。`jev-latest` 指向当前本地 Qwen 模型，支持结构化 instructions 和 criteria。

通过本地 `typesafe-ai` skill，向官方线上 API 发送过一条包含三种类型的合成请求。`jev-1.13.0` 返回 HTTP 200，验证了接口结构；这**不是正确率或速度对比**。

模型输出、限制、confidence 与用量定义存在差异。本地支持 2–255 个 Choice 选项、最多 64 个 Score 等级、64 个问题；TypeSafe 当前文档规定 Score 最多 10 级。部署限制以 `/v1/limits` 为准。

## 概率读数过程

1. 校验输入并安全解码图片。
2. 使用模型原生聊天模板，关闭 thinking。
3. 把选项映射到已验证的单 token 标签。
4. 对所有候选施加**相同的 +100 logit 偏置**，只请求一个 token 及采样后概率，禁用 top-k/top-p/min-p 截断和重复惩罚。
5. 检查返回列表包含所有候选，再归一化；缺失概率返回 502。
6. 根据分布直接计算类型化结果。

对给定候选，共同偏置会抵消：

```text
exp(logit_i + b) / sum_selected exp(logit_j + b)
  = exp(logit_i) / sum_selected exp(logit_j)
```

在浮点舍入误差范围内，相对赔率保持不变。偏置使候选进入返回列表；完整性检查确保不会虚构缺失标签的概率。仅靠 grammar 不足，因为已验证的 llama.cpp 版本可能在惰性语法过滤前返回概率。

Choice 取最大概率，Score 计算 `sum(等级索引 × 概率)`，confidence 是 1 减归一化熵。选项顺序与措辞会影响判断，这些数值不是经过校准的正确率保证。

## 图片链路

图片经过像素上限检查、EXIF 方向修正、RGB 转换、缩放和重新编码。API 从 `/props` 读取当前后端的媒体标记，通过原生视觉投影器输入模型，不是仅把 OCR 文字交给语言模型。

不支持远程抓取或请求指定的文件路径。模型可能受提示注入影响，业务上应将其视为可出错的输入，不能把模型概率直接当作安全授权。

## 参考项目

| 项目 | 方法 |
| --- | --- |
| [TypeSafe Jev](https://docs.typesafe.ai/api) | 托管的专有 SystemOne 模型 |
| [openjev-sglang](https://github.com/ekzhang/openjev-sglang) | SGLang 上的纯文字单 token Qwen 读数 |
| [AlexWortega/openjev](https://huggingface.co/AlexWortega/openjev) | 基于 Qwen3.5 微调的三分类 NLI 模型，含视觉检查点 |
| 本项目 | llama.cpp / Metal，文字与图片，单 token 类型化概率 |

NLI 模型的公开成绩不代表本实现。本站图表仅使用我们自己的 Qwen3.6 API 实测。项目参考了 [Hacker News 讨论](https://news.ycombinator.com/item?id=49752041)。
