# OpenJAV end-to-end delivery

Build a Jev-compatible local API with image input, real one-token probability readout, English and Chinese SEO documentation and an honest demo. Publish code and the documentation to Hand-In/openjav-multimodal, and verify deployment. All authored commits use 2026-10-01 (America/Los_Angeles).

Authority: the user requests autonomous end-to-end implementation and publication. The new, empty repository is the isolated project workspace. Work directly on the explicitly requested main branch. Avoid repeated approval gates for already authorized work. No paid services are required.

Proof: API tests, live text and image classification on this M3 Max, measured latency with complete provenance, reproducible setup, bilingual rendered pages, pushed main and an HTTP-verified GitHub Pages deployment.

Likely misfire: a JSON-generating chat wrapper with invented probabilities, a text-only model advertised as multimodal, publishing benchmark claims without actual hardware measurements, or treating static GitHub Pages as an inference host.

References: https://github.com/ekzhang/openjev-sglang ; https://news.ycombinator.com/item?id=49752041 ; https://huggingface.co/AlexWortega/openjev . The upstream SGLang repository has no license file at inspection; implement independently from its documented wire contract.
