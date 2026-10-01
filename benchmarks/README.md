# Measurement receipts

- quality/manifest.json: model, quantization, hardware, dataset revisions, original settings.
- quality/decisions.jsonl: all 886 completed observations. No GPQA question/answer text.
- quality/summary.json: 20-per-task displayed subset, exact IDs, Wilson intervals and timing.
- demo.json: two real local text/image calls shown on the website and GIF.
- contract-check.json: 255-option output and structured Chinese criteria.

The initial run planned 100 per task. It was stopped to reduce workload. The public chart uses the first 20 per task in fixed random order, without correctness-based selection. This is not a full benchmark or a measurement of TypeSafe Jev, Terra or the AlexWortega NLI checkpoint.

Use scripts/benchmark.py with --replay-report benchmarks/quality/summary.json to reproduce the public sample. New runs default to 20 per task, serial, with 250 ms rest between requests.
