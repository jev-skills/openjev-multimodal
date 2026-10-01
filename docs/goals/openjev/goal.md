# OpenJev Multimodal end-to-end delivery

Build a Jev-compatible local API with image input, real one-token probability readout, English and Chinese SEO documentation and an honest demo. Publish code and the documentation to Hand-In/openjev-multimodal, and verify deployment. All authored commits use 2026-10-01 (America/Los_Angeles).

Authority: the user requests autonomous end-to-end implementation and publication. The new, empty repository is the isolated project workspace. Work directly on the explicitly requested main branch. Avoid repeated approval gates for already authorized work. No paid services are required.

Proof: Live API calls, live text and image classification on this M3 Max, measured latency with complete provenance, reproducible setup, bilingual rendered pages, pushed main and an HTTP-verified GitHub Pages deployment.

Likely misfire: a JSON-generating chat wrapper with invented probabilities, a text-only model advertised as multimodal, publishing benchmark claims without actual hardware measurements, or treating static GitHub Pages as an inference host.

References: https://github.com/ekzhang/openjev-sglang ; https://news.ycombinator.com/item?id=49752041 ; https://huggingface.co/AlexWortega/openjev . The upstream SGLang repository has no license file at inspection; implement independently from its documented wire contract.

User steering: Superpowers globally disabled; do not use its approval/planning/test workflows. User requests a real nine-axis benchmark and a polished README chart using only our measured results.

Latest owner constraint: keep evaluation small and avoid heavy local load. The initial sequential run was interrupted at 886 completed cases; use the first 20 per task for the public chart, archive all completed records, and do not rerun the large evaluation. Only a handful of demo/contract calls remain authorized. One live TypeSafe Jev call succeeded through the local typesafe-ai skill.
