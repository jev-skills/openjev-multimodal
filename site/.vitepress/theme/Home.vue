<script setup>
import { computed, onMounted, ref } from 'vue'
import { useData, withBase } from 'vitepress'

const { lang } = useData()
const zh = computed(() => lang.value.startsWith('zh'))
const t = (en, cn) => zh.value ? cn : en
const route = name => withBase((zh.value ? '/zh/' : '/') + name)
const records = ref([])
const active = ref(0)
const replaying = ref(false)
const current = computed(() => records.value[active.value])
const answer = computed(() => current.value?.response.answers.decision)
const bars = computed(() => Object.entries(answer.value?.probabilities || {}))
onMounted(async () => {
  try { records.value = await (await fetch(withBase('/demo.json'))).json() } catch {}
})
function replay() {
  replaying.value = true
  setTimeout(() => { replaying.value = false }, 450)
}
</script>

<template>
  <div class="landing">
    <section class="hero-wrap">
      <div class="hero-grid">
        <div class="hero-copy">
          <div class="eyebrow"><span class="live-dot"></span>{{ t('OPEN MODELS. YOUR MACHINE.', '开放模型，运行在你的机器。') }}</div>
          <h1>{{ t('See. Decide.', '看见，即判断。') }}<br><span>{{ t('Stay local.', '一切留在本地。') }}</span></h1>
          <p class="hero-description">{{ t('Turn text and images into typed probabilities. A Jev-compatible API with one output token per question, running on your Mac.', '将文字与图片转为类型化概率。兼容 Jev API，每个问题仅一个输出 token，在你的 Mac 上完成推理。') }}</p>
          <div class="actions">
            <a class="button-primary" :href="route('guide')">{{ t('Start building', '立即开始') }} <span>↗</span></a>
            <a class="button-quiet" :href="route('benchmarks')">{{ t('See the benchmarks', '查看实测基准') }} →</a>
          </div>
          <div class="install-line"><span>$</span><code>uv run openjev serve</code><span class="install-hint">Apple Silicon + Metal</span></div>
        </div>
        <div class="hero-art" aria-label="Text and image input becoming a typed decision">
          <div class="orb orbit-one"></div><div class="orb orbit-two"></div>
          <div class="floating-label top-label">INPUT / 输入</div>
          <div class="input-tile text-tile"><span class="tile-icon">Aa</span><span>{{ t('Text & context', '文字与上下文') }}</span><i></i><i></i><i></i></div>
          <div class="input-tile image-tile"><svg viewBox="0 0 90 64" aria-hidden="true"><rect width="90" height="64" rx="6" fill="#253829"/><circle cx="64" cy="17" r="8" fill="#b4f784"/><path d="M0 64 29 21 59 64M37 64 67 33 90 64" fill="#63866a"/></svg><span>{{ t('Images & frames', '图片与画面') }}</span></div>
          <div class="flow-line"></div>
          <div class="decision-node"><svg viewBox="0 0 40 40" aria-hidden="true"><path d="m20 3 17 17-17 17L3 20Z" fill="currentColor"/><circle cx="20" cy="20" r="6" fill="#111a13"/></svg></div>
          <div class="output-tile"><div class="output-top"><span>SystemOne</span><span class="token-pill">1 TOKEN</span></div><code><span class="code-dim">{</span><br>&nbsp;&nbsp;{{ t('"type"', '"type"') }}: <em>"choice"</em>,<br>&nbsp;&nbsp;"probabilities": <em>{ … }</em><br><span class="code-dim">}</span></code><div class="output-foot"><span class="live-dot"></span>{{ t('Typed. Composable. Local.', '类型明确 · 轻松组合 · 本地运行') }}</div></div>
          <div class="floating-label bottom-label">DECISIONS AS A PRIMITIVE</div>
        </div>
      </div>
      <div class="proof-strip">
        <div><strong>1 <span>token</span></strong><p>{{ t('per question · no generated reasoning', '每个问题 · 无推理文本生成') }}</p></div>
        <div><strong>3 <span>{{ t('primitives', '种原语') }}</span></strong><p>Noul · Choice · Score</p></div>
        <div><strong>255 <span>{{ t('options', '个选项') }}</span></strong><p>{{ t('complete label distributions', '完整的候选概率分布') }}</p></div>
        <div><strong>100% <span>local</span></strong><p>{{ t('inference stays on your machine', '推理数据留在你的机器') }}</p></div>
      </div>
    </section>

    <section class="section demo-section" id="demo">
      <div class="section-heading"><div><div class="eyebrow">01 / {{ t('FROM INPUT TO ACTION', '从输入到行动') }}</div><h2>{{ t('A small API.', '一个小 API。') }}<br>{{ t('A useful kind of intelligence.', '一种实用的智能。') }}</h2></div><p>{{ t('Route a message. Read a screen. Choose the next step. The response is already structured for your code.', '分流消息，读取画面，选择下一步。返回值天然结构化，可以直接接入业务代码。') }}</p></div>
      <div class="demo-shell">
        <div class="demo-toolbar"><div class="demo-tabs"><button :class="{selected:active===0}" @click="active=0">{{ t('Text → route', '文字 → 分流') }}</button><button :class="{selected:active===1}" @click="active=1">{{ t('Image → decision', '图片 → 判断') }}</button></div><span class="recorded-badge">{{ t('RECORDED LOCAL RUN', '本机实测回放') }}</span></div>
        <div class="demo-body">
          <div class="demo-input"><div class="panel-label">{{ t('STATE', '输入状态') }}<span>{{ current?.model || 'Qwen3.6-35B-A3B' }}</span></div><template v-if="current"><img v-if="current.image" :src="withBase(current.image)" :alt="t('Synthetic checkout screenshot used in the real local run', '真实本机运行使用的合成支付截图')" class="demo-image"><blockquote v-else>{{ current.state }}</blockquote><div class="question-label">{{ t('QUESTION', '问题') }}</div><p class="demo-question">{{ current.question }}</p></template><p v-else>{{ t('Loading recorded result…', '正在加载实测结果…') }}</p><button class="replay-button" @click="replay" :disabled="!current || replaying">▶ {{ t('Replay response', '回放响应') }}</button></div>
          <div class="demo-output"><div class="panel-label">RESPONSE<span class="token-pill">{{ current?.response.usage.output_tokens || 1 }} OUTPUT TOKEN</span></div><div class="result-heading"><span class="result-check">✓</span><strong>{{ answer?.choice || '…' }}</strong><span>{{ t('choice', '分类结果') }}</span></div><div class="distribution" v-for="[name, probability] in bars" :key="name"><div><span>{{ name }}</span><b>{{ (probability*100).toFixed(2) }}%</b></div><div class="bar-track"><div class="bar-fill" :style="{width:(replaying ? 0 : probability*100)+'%'}"></div></div></div><div class="result-meta"><span>{{ current ? Math.round(current.elapsed_ms)+' ms' : '—' }}<small>{{ t('measured HTTP latency', '实测 HTTP 延迟') }}</small></span><span>{{ current?.response.usage.input_tokens || '—' }}<small>{{ t('input tokens', '输入 token') }}</small></span></div></div>
        </div>
        <div class="demo-caption">{{ t('Replay of an actual local API response. Run the playground on localhost to try your own inputs. Scores are conditional on the supplied options.', '以上是实际本地 API 响应的回放。在 localhost 运行 playground 即可使用自己的输入。概率以给定候选选项为条件。') }} <a :href="route('examples')">{{ t('Try it →', '动手试试 →') }}</a></div>
      </div>
    </section>

    <section class="section primitives">
      <div class="eyebrow">02 / {{ t('PROGRAM WITH PROBABILITIES', '用概率编程') }}</div>
      <h2>{{ t('Three ways to make a decision.', '三种方式，表达你的判断。') }}</h2>
      <div class="primitive-grid">
        <article><span class="primitive-symbol">01</span><h3>Noul <span>→ float</span></h3><p>{{ t('Is it true? A yes/no judgment expressed as a probability you can threshold.', '是否成立？用 0–1 概率表达是非判断，自由设定业务阈值。') }}</p><code>if refund.noul &gt; 0.9:<br>&nbsp;&nbsp;review_payment()</code></article>
        <article><span class="primitive-symbol">02</span><h3>Choice <span>→ enum</span></h3><p>{{ t('Which one? Select an option and inspect the complete distribution.', '选择哪一个？返回最优候选及完整概率分布，支持最多 255 个选项。') }}</p><code>route = answer.choice<br>dispatch[route](ticket)</code></article>
        <article><span class="primitive-symbol">03</span><h3>Score <span>→ float</span></h3><p>{{ t('How much? Get the expected position on your ordered rubric.', '程度如何？定义有序评分标准，返回期望等级与各级概率。') }}</p><code>priority = urgency.score<br>queue.add(item, priority)</code></article>
      </div>
    </section>

    <section class="section benchmark-section">
      <div class="section-heading"><div><div class="eyebrow">03 / {{ t('MEASURED, ON A MAC', '在 MAC 上，真实测量') }}</div><h2>{{ t('Show the work.', '让数据说话。') }}</h2></div><p>{{ t('Nine tasks. Our API. Reproducible inputs, per-question receipts, and a clear account of what was measured.', '九类任务，只测我们的 API。可复现的输入、逐题记录，以及清楚说明的测试边界。') }}</p></div>
      <a :href="route('benchmarks')" class="chart-link"><img :src="withBase('/benchmark.png')" loading="lazy" width="1800" height="1120" :alt="t('Measured OpenJev Multimodal benchmark scores with sample counts; see the accessible data table on the benchmark page.', 'OpenJev Multimodal 实测基准与样本量；详细数据表见基准页面。')"></a>
      <div class="benchmark-note"><span>{{ t('Zero-shot · One-token readout · 20 samples per task · Seed 42', '零样本 · 单 token 读数 · 每项 20 题 · 随机种子 42') }}</span><a :href="route('benchmarks')">{{ t('Methodology & raw results ↗', '方法与原始结果 ↗') }}</a></div>
    </section>

    <section class="section closing">
      <div class="eyebrow">BUILT FOR YOUR NEXT IDEA</div><h2>{{ t('Your state.', '你的状态。') }}<br><span>{{ t('Your model. Your decision.', '你的模型，你的决定。') }}</span></h2><p>{{ t('Start with a lightweight 4B model. Scale to Qwen3.6 or Qwen3.8 on a larger Mac. Keep the same API.', '从轻量的 4B 模型起步，在大内存 Mac 上切换至 Qwen3.6 或 Qwen3.8，保持同一套 API。') }}</p><div class="actions"><a class="button-primary" :href="route('guide')">{{ t('Run it locally', '本地运行') }} ↗</a><a class="button-quiet" href="https://github.com/jev-skills/openjev-multimodal">GitHub →</a></div>
    </section>
  </div>
</template>
