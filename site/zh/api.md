---
title: SystemOne API 参考 — 概率、分类与评分
description: Jev 兼容的请求和响应格式，多模态图片输入，Noul、Choice、Score，鉴权、用量、限制与错误码。
---

# API 参考

地址：`http://127.0.0.1:8000`。使用 JSON。如已设置 `OPENJEV_API_KEY`，访问 `/v1/*` 需携带 `Authorization: Bearer YOUR_KEY`。

## POST /v1/systemone

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `model` | 字符串 | `jev-latest`、`openjev-latest` 或当前模型 ID，默认 `jev-latest` |
| `state` | 字符串、对象或数组 | 待评估的共同上下文 |
| `questions` | 对象 | 1–64 个命名问题 |
| `images` | 字符串数组 | 扩展字段，最多 8 张 PNG/JPEG/WebP data URL |

支持普通 JSON、聊天消息数组，以及只有一个 `messages` 字段的对象。聊天内容支持文字及 OpenAI 风格的 `text` / `image_url` 部件。如果对象在 `messages` 之外还有字段，会完整保留为 JSON，避免丢失业务信息。

`instructions` 和标准描述支持字符串、对象、数组。问题 ID 只用于关联响应，不传给模型；Choice 选项键也不会展示给模型，描述为 `null` 时例外，此时使用键作为含义。

## Noul：成立概率

```json
{
  "type": "noul",
  "instructions": "用户是否要求退款？",
  "criteria": { "true": "提出了退款要求", "false": "没有退款要求" }
}
```

`criteria` 可省略，默认为 Yes / No。响应：

```ts
{ type: "noul"; noul: number } // true 对应的概率，范围 0–1
```

接近 0.5 表示两种判断相近，不表示“中等强度”。

## Choice：选项与完整分布

```json
{
  "type": "choice",
  "instructions": "应交给哪个团队？",
  "criteria": {
    "billing": { "负责": ["支付", "退款"] },
    "technical": "软件故障",
    "other": null
  }
}
```

提供 2–255 个选项。

```ts
{
  type: "choice";
  choice: string; // 原始选项键
  probabilities: Record<string, number>; // 包含所有选项，总和为 1
  confidence: number; // 0–1
}
```

## Score：评分等级的期望值

```json
{
  "type": "score",
  "instructions": "此请求有多紧急？",
  "criteria": ["常规", "紧急", "严重事故"]
}
```

提供 2–64 个从低到高的等级，索引从 0 开始。

```ts
{
  type: "score";
  score: number; // sum(等级索引 × 概率)，范围 0 到等级数减 1
  legend: Record<string, string>;
  probabilities: Record<string, number>;
  confidence: number;
}
```

结构化等级描述在 `legend` 中序列化为 JSON 字符串。

## 响应与用量

```ts
{
  model: string; // 请求使用的别名或 ID
  answers: Record<string, NoulAnswer | ChoiceAnswer | ScoreAnswer>;
  usage: { input_tokens: number; output_tokens: number };
  timing?: {                // OpenJev 扩展字段，单位毫秒
    processing_ms: number;  // 服务器从收到请求到结果就绪
    parse_ms: number;       // 读取、解析并校验请求
    prepare_ms: number;     // 整理 state、处理图片、编译提示
    queue_ms: number;       // 等待推理槽位
    inference_ms: number;   // 共享前缀预填充与逐题读数
  };
}
```

输入用量是各问题的完整后端提示 token 数之和，包含图片与缓存 token；输出用量等于问题数。这不是 TypeSafe 的计费单位。

`timing` 让你无需在客户端埋点即可查看服务端耗时：`processing_ms` 从 API 收到请求起算，到响应就绪为止，不含网络传输；各阶段之和与它的差距不到 1 毫秒。`model`、`answers`、`usage` 仍与 Jev 完全一致：官方 Python SDK 以 `extra="ignore"` 解析响应，JavaScript SDK 直接返回解析后的 JSON，二者都会忽略这个扩展字段。如果客户端会拒绝未知字段，设置 `OPENJEV_RESPONSE_TIMING=false` 即可，下列响应头仍提供相同数据。

| 响应头 | 含义 |
| --- | --- |
| `x-typesafe-request-id` | 唯一请求 ID |
| `x-openjev-model` | 实际后端模型 |
| `x-openjev-cached-tokens` | 后端报告的复用 token 数 |
| `x-openjev-processing-ms` | 服务端处理耗时；所有 `/v1/*` 错误响应也会返回 |
| `x-openjev-elapsed-ms` | 评估耗时：从整理 state 到最后一次读数 |
| `Server-Timing` | `parse`、`prepare`、`queue`、`inference`、`total`，以及 llama.cpp 报告的模型计算时间 `compute` |

浏览器开发者工具的 Timing 面板会直接显示 `Server-Timing`。

概率以给定候选为条件。`confidence = 1 − H(p)/log(n)` 衡量分布集中度，不是校准后的正确率保证。

## 发现与健康检查

| 路径 | 用途 |
| --- | --- |
| `GET /v1/models` | TypeSafe 与 OpenAI 风格模型目录 |
| `GET /v1/limits` | 当前部署限制 |
| `GET /health` | 检查推理后端并返回后端名称、模型、权重文件与版本；不可用时返回 503 |
| `GET /health/live` | API 进程存活 |
| `GET /docs` | 交互文档 |
| `GET /openapi.json` | OpenAPI schema |
| `GET /playground` | 本地文字与图片演示 |

默认上限：16 MiB 请求体、每个分支含输出 8,192 个估算 token、总输入 131,072 token、8 张图、每图解码后 2,000 万像素、缩放最长边 1,024 像素、总超时 120 秒。图片 token 准入采用保守估算，后端也会检查实际上下文。

## 错误

```json
{ "error": { "message": "可读的错误说明" } }
```

| 状态码 | 含义 |
| --- | --- |
| `401` | 密钥缺失或无效 |
| `413` | 请求或解码图片过大 |
| `422` | 格式、模型、图片、模态或 token 限制错误 |
| `502` | 概率不完整或后端不兼容 |
| `503` | 后端不可用 |
| `504` | 总超时 |
| `529` | 排队已满，按 `Retry-After` 重试 |

校验错误会包含字段位置，不回显私密输入。
