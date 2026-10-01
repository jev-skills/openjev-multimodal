---
title: 快速开始 — 在 Mac 本地运行 Jev 兼容 API
description: 使用 uv 与 llama.cpp 安装 OpenJev Multimodal，在 Apple Silicon 上运行 Qwen，体验文字与图片的类型化决策。
---

# 从本地开始

需要 Apple Silicon Mac、Python 3.11+，以及足以容纳模型的内存。16 GB 或更大内存的 Mac 可以从 4B 的 `balanced` 档开始；更看重内存占用时选择 `fast`。这是选型起点，不是实测最低内存保证。

## 安装并启动

```bash
brew install uv llama.cpp
git clone https://github.com/Hand-In/openjev-multimodal.git
cd openjev-multimodal
uv sync --frozen
uv run openjev serve
```

第一次启动会下载固定版本的模型与视觉投影器，之后复用 Hugging Face 本地缓存。打开 **[localhost:8000/playground](http://localhost:8000/playground)** 即可上传图片、输入文字；**[localhost:8000/docs](http://localhost:8000/docs)** 提供可交互的 API 文档。

已验证的 llama.cpp 版本为 **b9670**。需要该版本或更新版本，并支持 `/props.media_marker` 与 `post_sampling_probs`；旧版 Homebrew 安装请先升级。

## 第一次判断

```bash
curl http://127.0.0.1:8000/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "jev-latest",
    "state": "我被重复扣款了，请退还多扣的一笔。",
    "questions": {
      "refund": {
        "type": "noul",
        "instructions": "用户是否要求退款？"
      },
      "team": {
        "type": "choice",
        "instructions": "应交给哪个团队？",
        "criteria": {
          "billing": "付款与退款",
          "technical": "软件故障"
        }
      }
    }
  }'
```

返回退款概率、所选团队、全部候选概率及用量。两个问题只使用**两个输出 token**。输入预填充仍有成本，长上下文和图片会增加耗时。

## 模型档位

```bash
uv run openjev serve --profile fast      # Qwen3.5-0.8B Q4_K_M
uv run openjev serve --profile balanced  # Qwen3.5-4B Q4_K_M，默认
uv run openjev serve --profile quality   # Qwen3.6-35B-A3B UD-Q4_K_XL
```

一次只运行一个档位。默认一个推理槽位、四个 CPU 线程；`--threads 2` 可进一步限制 CPU。按 **Ctrl+C** 退出，CLI 会停止自己启动的后端。

## 使用已有模型

```bash
uv run openjev serve --profile quality \
  --model-file /path/to/model.gguf \
  --mmproj-file /path/to/mmproj.gguf

uv run openjev serve --connect http://127.0.0.1:18081
```

权重必须配套对应的视觉投影器。已有后端需提供 llama.cpp 原生接口，支持采样后概率，关闭 thinking，使用单槽位；其上下文与图片 token 限制应和 `--context`、`--image-tokens` 一致。

## 配置

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `--port` | `8000` | API 与本地演示页 |
| `--backend-port` | `18081` | 仅本机可访问的推理后端 |
| `--context` | `8192` | 每个问题的上下文上限 |
| `--image-tokens` | `512` | 每张图片的后端 token 预算 |
| `--threads` | `4` | CPU 与预填充线程 |
| `OPENJEV_API_KEY` | 未设置 | 为 `/v1/*` 启用 Bearer 鉴权 |
| `OPENJEV_REQUEST_TIMEOUT` | `120` | 总超时秒数，含排队 |
| `OPENJEV_MAX_CONCURRENT_REQUESTS` | `4` | 活跃或排队请求上限；推理仍串行 |
| `OPENJEV_IMAGE_MAX_EDGE` | `1024` | 缩放后图片最长边 |
| `OPENJEV_IMAGE_ALIGN` | `32` | 视觉 token 边长（像素）；超大图片一次缩放到编码器实际尺寸，设为 `0` 关闭 |
| `OPENJEV_PRIME_SHARED_PREFIX` | `true` | 多问题请求只读取一次共享 state |
| `OPENJEV_TEMPLATE_CACHE` | `true` | 复用经后端核验的聊天模板骨架 |
| `OPENJEV_RESPONSE_TIMING` | `true` | 在响应中加入 `timing` 对象；响应头始终包含耗时 |

可通过环境变量或本地 `.env` 设置，密钥不要提交到 Git。服务默认绑定 `127.0.0.1`。如需主动对外开放，请配置鉴权和 TLS 反向代理。

```bash
uv run openjev doctor
curl http://127.0.0.1:8000/health
uv run openjev schema > openapi.json
```

GitHub Pages 托管静态文档，推理 API 运行在你的 Mac 上。
