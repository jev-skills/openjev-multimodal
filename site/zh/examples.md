---
title: 多模态示例 — 图片判断、路由与评分
description: 使用 Python 和 JavaScript 调用本地 Jev 兼容 API，将图片和文字转为可直接使用的结构化决策。
---

# 文字与视觉示例

## 识别本地图片

调用本地 API 时，图片留在本机。data URL 无需远程抓取，也不开放服务端文件路径访问。

```python
import base64
from pathlib import Path
import httpx

image = base64.b64encode(Path("screenshot.png").read_bytes()).decode()
response = httpx.post("http://127.0.0.1:8000/v1/systemone", json={
    "model": "jev-latest",
    "state": "一张结账截图，请读取支付状态。",
    "images": ["data:image/png;base64," + image],
    "questions": {
        "decision": {
            "type": "choice",
            "instructions": "画面显示哪种支付状态？",
            "criteria": {
                "paid": "支付成功",
                "pending": "支付处理中",
                "failed": "支付失败"
            }
        }
    }
}, timeout=120)
response.raise_for_status()
print(response.json()["answers"]["decision"])
```

仓库附有可直接运行的合成支付截图示例：

```bash
uv run python examples/image_decision.py examples/checkout.png
```

## 多模态聊天

```json
{
  "model": "jev-latest",
  "state": {
    "messages": [{
      "role": "user",
      "content": [
        { "type": "text", "text": "读取这张结账截图。" },
        { "type": "image_url", "image_url": { "url": "data:image/png;base64,..." } }
      ]
    }]
  },
  "questions": {
    "paid": {
      "type": "noul",
      "instructions": "画面是否确认付款成功？"
    }
  }
}
```

将省略号换成真实 base64。支持 PNG、JPEG、WebP；不接受远程图片 URL、文件 URL、动图、原始音频或原生视频。可以自行抽取少量视频帧，按顺序作为图片发送，并在 state 中附时间戳；这不等同于具备运动理解的视频模型。

## JavaScript

```js
const response = await fetch("http://127.0.0.1:8000/v1/systemone", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "jev-latest",
    state: { ticket: "付款连续失败三次。", account: "企业客户" },
    questions: {
      route: {
        type: "choice",
        instructions: "选择客服团队。",
        criteria: { billing: "支付问题", product: "产品功能", other: "其他" }
      },
      urgency: {
        type: "score",
        instructions: "请求有多紧急？",
        criteria: ["常规", "需要尽快处理", "服务不可用"]
      }
    }
  })
});
if (!response.ok) throw new Error(await response.text());
const { answers } = await response.json();
console.log(answers.route.choice, answers.urgency.score);
```

该示例适用于 Node.js 或同源应用。静态文档站不会访问 localhost 或代理密钥，浏览器实验请打开本地 playground。

## 在代码中组合判断

把算术、规则与执行保留在业务代码中。问题尽量具体，候选不完整时添加“其他”或“无匹配”；使用真实业务数据评估阈值。

多个独立条件可以同时成立时，分别使用 Noul。Choice 比较互斥候选；Score 表示有序等级的期望值，可以落在两个等级之间。
