import { defineConfig } from 'vitepress'

const base = '/openjev-multimodal/'
const host = 'https://hand-in.github.io'
const menu = (zh = false) => [
  { text: zh ? '开始使用' : 'Get started', items: [
    { text: zh ? '快速开始' : 'Quickstart', link: zh ? '/zh/guide' : '/guide' },
    { text: zh ? 'API 参考' : 'API reference', link: zh ? '/zh/api' : '/api' },
    { text: zh ? '多模态示例' : 'Multimodal examples', link: zh ? '/zh/examples' : '/examples' },
  ] },
  { text: zh ? '深入了解' : 'Go deeper', items: [
    { text: zh ? '模型与性能' : 'Models & performance', link: zh ? '/zh/models' : '/models' },
    { text: zh ? '基准测试' : 'Benchmarks', link: zh ? '/zh/benchmarks' : '/benchmarks' },
    { text: zh ? '设计与兼容性' : 'Design & compatibility', link: zh ? '/zh/design' : '/design' },
  ] },
]
export default defineConfig({
  base, title: 'OpenJev Multimodal', cleanUrls: true,
  ignoreDeadLinks: [/^http:\/\/localhost:8000\//],
  description: 'A local, open-source Jev-compatible API for typed decisions from text and images. One-token probabilities on Apple Silicon with Qwen 3.5 and Qwen 3.6.',
  lastUpdated: false,
  sitemap: { hostname: host + base },
  head: [
    ['link', { rel: 'icon', type: 'image/svg+xml', href: base + 'logo.svg' }],
    ['meta', { name: 'theme-color', content: '#101713' }],
    ['meta', { property: 'og:site_name', content: 'OpenJev Multimodal' }],
    ['meta', { property: 'og:type', content: 'website' }],
    ['meta', { property: 'og:image', content: host + base + 'social.png' }],
    ['meta', { name: 'twitter:card', content: 'summary_large_image' }],
    ['meta', { name: 'twitter:image', content: host + base + 'social.png' }],
    ['script', { type: 'application/ld+json' }, JSON.stringify({
      '@context': 'https://schema.org', '@type': 'SoftwareApplication',
      name: 'OpenJev Multimodal', applicationCategory: 'DeveloperApplication',
      operatingSystem: 'macOS', softwareVersion: '0.1.0',
      url: host + base, license: 'https://opensource.org/license/mit',
      description: 'Local Jev-compatible typed decisions from text and images on Apple Silicon.',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
    })],
  ],
  transformHead({ pageData }) {
    const relative = pageData.relativePath.replace(/index\.md$/, '').replace(/\.md$/, '')
    const neutral = relative.replace(/^zh\//, '')
    const title = pageData.title ? pageData.title + ' | OpenJev Multimodal' : 'OpenJev Multimodal'
    const description = pageData.description || 'Local typed AI decisions from text and images on your Mac.'
    return [
      ['link', { rel: 'canonical', href: host + base + relative }],
      ['link', { rel: 'alternate', hreflang: 'en', href: host + base + neutral }],
      ['link', { rel: 'alternate', hreflang: 'zh-CN', href: host + base + 'zh/' + neutral }],
      ['link', { rel: 'alternate', hreflang: 'x-default', href: host + base + neutral }],
      ['meta', { property: 'og:title', content: title }],
      ['meta', { property: 'og:description', content: description }],
      ['meta', { property: 'og:url', content: host + base + relative }],
      ['meta', { property: 'og:locale', content: relative.startsWith('zh/') ? 'zh_CN' : 'en_US' }],
    ]
  },
  locales: {
    root: { label: 'English', lang: 'en', themeConfig: {
      nav: [{ text: 'Docs', link: '/guide' }, { text: 'Benchmarks', link: '/benchmarks' }],
      sidebar: menu(), footer: { message: 'Open models. Local inference. Measured claims.', copyright: 'MIT · OpenJev Multimodal' },
    } },
    zh: { label: '简体中文', lang: 'zh-CN', title: 'OpenJev Multimodal',
      description: '可在 Mac 本地运行的开源 Jev 兼容多模态 API。将文字与图片转为类型化概率，支持 Qwen3.5、Qwen3.6 和 Apple Silicon。',
      themeConfig: { nav: [{ text: '文档', link: '/zh/guide' }, { text: '基准测试', link: '/zh/benchmarks' }],
        sidebar: menu(true), outlineTitle: '本页内容',
        footer: { message: '开放模型 · 本地推理 · 实测数据', copyright: 'MIT · OpenJev Multimodal' },
      },
    },
  },
  themeConfig: {
    logo: '/logo.svg', siteTitle: 'OpenJev',
    socialLinks: [{ icon: 'github', link: 'https://github.com/Hand-In/openjev-multimodal' }],
    search: { provider: 'local' }, outline: [2, 3],
  },
})
