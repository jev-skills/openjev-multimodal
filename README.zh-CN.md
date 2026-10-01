<p align="center"><img src="assets/social.png" alt="OpenJev Multimodal — 文字与图片，本地决策" width="900"></p>

<p align="center"><a href="https://hand-in.github.io/openjev-multimodal/zh/">中文文档</a> · <a href="README.md">English</a> · <a href="https://hand-in.github.io/openjev-multimodal/zh/benchmarks">实测基准</a></p>

# OpenJev Multimodal

**文字与图片 → 类型化决策。每个问题一个输出 token，在你的 Mac 本地运行。**

基于 Qwen 与 llama.cpp / Metal 的开源 **Jev 兼容 SystemOne API**。支持消息分流、截图理解、规则评分与下一步选择，返回完整概率分布。

- **三种原语**：Noul 成立概率、Choice 分类与分布、Score 等级期望。
- **原生视觉**：PNG/JPEG/WebP、多模态聊天、少量视频抽帧。
- **单 token 读数**：无需生成思维链或逐字输出 JSON。
- **255 个选项**：验证单 token 标签，检查完整候选概率。
- **本地推理**：输入与图片留在本机，无需付费推理 API。
- **可控资源**：默认单推理槽位、四个 CPU 线程。

独立实现，与 TypeSafe 无隶属关系，不含其专有 Jev 权重。概率以候选为条件，不是校准后的正确率保证。

## 启动

需要 Apple Silicon、Python 3.11+，以及支持采样后概率的 llama.cpp b9670 或更新版本。

```bash
brew install uv llama.cpp
git clone https://github.com/Hand-In/openjev-multimodal.git
cd openjev-multimodal
uv sync --frozen
uv run openjev serve
```

打开 **http://localhost:8000/playground** 体验文字与图片；**http://localhost:8000/docs** 是交互文档。首次下载固定版本权重，之后复用缓存。Ctrl+C 会停止 API 和其后端。

| 档位 | 模型 | 量化 | 定位 |
| --- | --- | --- | --- |
| `fast` | Qwen3.5-0.8B | Q4_K_M | 低占用、简单判断 |
| `balanced`，默认 | Qwen3.5-4B | Q4_K_M | 日常文字与图片 |
| `quality` | Qwen3.6-35B-A3B | UD-Q4_K_XL | 大内存 Mac、较强知识能力 |

```bash
uv run openjev serve --profile quality
uv run openjev doctor
```

一次只运行一个档位。quality 权重约 23.3 GB、投影器约 0.9 GB。实测来自 M3 Max 128 GB，未测其他机器的最低内存要求。

## API 示例

```bash
curl http://127.0.0.1:8000/v1/systemone \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "jev-latest",
    "state": "我被重复扣款了，请退款。",
    "questions": {
      "team": {
        "type": "choice",
        "instructions": "应交给哪个团队？",
        "criteria": {"billing": "支付与退款", "technical": "软件故障"}
      }
    }
  }'
```

读取 `answers.team.choice` 和 `answers.team.probabilities`。添加 `images` data URL 数组即可输入图片。[完整 API →](https://hand-in.github.io/openjev-multimodal/zh/api)

## 本机实录

![文字路由与图片判断的实际响应回放](assets/demo.gif)

动图回放**真实本地 API 结果**，耗时来自实测。结账图为原创合成素材。文档站回放记录，本地 playground 实时推理。[响应记录](benchmarks/demo.json) · [图片示例](examples/image_decision.py)。

## 俄罗斯方块：限时决策

[![Qwen3.5-4B 通过 OpenJev Multimodal 玩俄罗斯方块](examples/tetris/report/videos/balanced.jpg)](https://hand-in.github.io/openjev-multimodal/zh/tetris)

三个本地模型通过 API 玩俄罗斯方块。代码枚举所有合法的两步方案并负责按键；**1 个 Choice token 选出方案**，依据是精确的文字事实与按 token 对齐的结果图。视觉模式的 15 局全部完成 10 次消除，单次决策中位数为 0.15 秒（0.8B）、0.65 秒（4B）和 0.91 秒（35B-A3B）。[演示页](https://hand-in.github.io/openjev-multimodal/zh/tetris) · [在浏览器中试玩](https://hand-in.github.io/openjev-multimodal/demos/tetris/web/) · [测试报告](examples/tetris/report/README.zh-CN.md) · [代码](examples/tetris)。

## 在智能体中使用

```bash
npx openskills install Hand-In/openjev-multimodal/skills/openjev-multimodal -g -y
```

[openjev-multimodal 技能](skills/openjev-multimodal)教 Claude Code、Codex 以及任何读取 `AGENTS.md` 的智能体启动与检查服务、设计 Noul / Choice / Score 问题、按视觉编码器调整图片尺寸，并读取概率与延迟。在本地克隆中可直接运行 `npm run skill:install`。

## 小样本基准

![九类任务，每项 20 题，包含置信区间](assets/benchmark.png)

**只绘制我们的 API。** Qwen3.6-35B-A3B UD-Q4_K_XL · llama.cpp b9670 · M3 Max · 零样本 · 单输出 token · **每项 20 题，图中共 180 次判断**。所选文字任务 HTTP 延迟中位数 **281 ms**。

这是探索性抽样，不是排行榜成绩。图中展示 Wilson 区间；GSM8K 使用合成数字干扰项，国际象棋测试合法着法。较大评测已中断以控制负载，886 条已完成记录全部保留；图表按各任务随机顺序取前 20 条，没有按成绩筛选。

[方法](https://hand-in.github.io/openjev-multimodal/zh/benchmarks) · [汇总与 ID](benchmarks/quality/summary.json) · [全部记录](benchmarks/quality/decisions.jsonl) · [SVG 图](assets/benchmark.svg)。

```bash
# quality 服务启动后，小样本串行运行，每次请求后休息
uv run --group bench python scripts/benchmark.py \
  --samples 20 --cooldown 0.25 --output benchmarks/local

# 只根据已有记录画图，不执行推理
uv run --group bench python scripts/render_benchmark.py
```

## 原理与边界

选项映射为单 token 标签，通过共同 logit 偏置取得完整候选概率，再归一化抵消偏置。输入预填充、图像编码、模型和缓存仍影响耗时，每个响应都会返回服务端耗时。[原理 →](https://hand-in.github.io/openjev-multimodal/zh/design) · [延迟 →](https://hand-in.github.io/openjev-multimodal/zh/performance)

- 默认 localhost；`OPENJEV_API_KEY` 启用 `/v1/*` Bearer 鉴权。
- `/health` 检查后端，`/health/live` 检查进程，`/v1/limits` 返回限制。
- 限制请求体、队列、解码图片和超时，后端出错时明确报错。
- 不抓取远程图片，不开放请求指定的文件读取。
- 不支持原始音频和原生视频，可输入少量抽帧。
- `--connect` 连接已有兼容后端。
- GitHub Pages **只托管静态文档**，推理在 Mac 上执行。

## 参考与许可

参考 [openjev-sglang](https://github.com/ekzhang/openjev-sglang)、[AlexWortega/openjev](https://huggingface.co/AlexWortega/openjev)、[HN](https://news.ycombinator.com/item?id=49752041) 和 [TypeSafe API](https://docs.typesafe.ai/api)。NLI 模型的公开成绩不代表本实现；一次合成请求验证了线上 Jev 的接口结构，不进入基准对比。

原创代码 [MIT](LICENSE)，模型与数据集保留各自许可。详见 [NOTICE](NOTICE)。
