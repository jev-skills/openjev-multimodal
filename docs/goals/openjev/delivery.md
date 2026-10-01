# Delivery receipt

Publication verified on September 21, 2026. Commit author and committer dates are intentionally October 1, 2026, as requested; they are not the measurement dates.

- Repository: https://github.com/Hand-In/openjev-multimodal
- English documentation: https://hand-in.github.io/openjev-multimodal/
- Chinese documentation: https://hand-in.github.io/openjev-multimodal/zh/
- Benchmark: https://hand-in.github.io/openjev-multimodal/zh/benchmarks
- Local playground: http://127.0.0.1:8000/playground

## Evidence

The published implementation at `7a9f074` passed the [package workflow](https://github.com/Hand-In/openjev-multimodal/actions/runs/35578015450) and [documentation deployment](https://github.com/Hand-In/openjev-multimodal/actions/runs/35578015512). English/Chinese homepages, quickstart, API and benchmark pages returned HTTP 200, as did the benchmark image, recorded demo JSON, social image, sitemap, robots.txt and llms.txt. Homepages include canonical URLs, language alternates, OpenGraph metadata and JSON-LD. Desktop and 390px mobile views were visually reviewed; the published benchmark page renders its figure and accessible table.

Real inference receipts are in `benchmarks/contract-check.json`, `benchmarks/demo.json` and `benchmarks/local-deployment.json`. They cover complete 255-label probabilities, all three primitives, structured Chinese input, real text/image decisions and the final balanced deployment. A single synthetic online TypeSafe Jev request verified the common wire shape; no hosted model scores enter our benchmark. Credentials and private local logs are not published.

The public quality-model chart uses 20 cases per task, 180 total, selected by the first IDs in the existing fixed random order. All 886 completed observations from the interrupted larger run are retained in `benchmarks/quality/decisions.jsonl`; no additional batch was run after the owner requested small samples. Selection, dataset versions, uncertainty and adapted GSM8K/chess definitions are documented. Recorded demos are visibly labeled as replays.

The final local service is Qwen3.5-4B with a matching vision projector, one inference slot and four CPU threads. The larger quality model has been stopped. The 4B process is detached for the current machine session; no login or boot autostart was installed. The CLI's normal `serve` command can restart it. GitHub Pages hosts static documentation; inference remains on localhost.

## Completion audit

The delivered behavior matches the requested local multimodal typed API, bilingual documentation, real demo/GIF, honest sampled benchmark, corrected repository name and public deployment. There is no generated-JSON substitute for probability readout and no claim to use TypeSafe's proprietary model weights. The chart reports actual local observations, not upstream scores. No unit-test suite was added or run, following the owner's instruction; real API calls, lint, package construction and documentation builds supplied the verification evidence. Superpowers is disabled in the user's global Codex plugin configuration.

Accuracy and latency are workload-dependent; the 180-case chart is exploratory. Native audio/video and remote image fetching are outside the documented API. Multiple supplied images support sampled frames. These limits do not leave any requested deliverable unfinished.
