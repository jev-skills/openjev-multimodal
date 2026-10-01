# Learn from Inco Splash; faster model downloads

Wrap up the max-profile work. Then find out why Inco Splash (https://inco.ai/blog/splash/, https://huggingface.co/incoai/Qwen3.8-27B-Splash) runs Qwen3.8-27B so fast on a Mac and whether it is open source. The owner will not upgrade this Mac's operating system, so check whether Splash's source can be applied here to improve OpenJev's prefill and cache performance. Also find faster channels for downloading models, and research and build that end to end.

Authority: the owner requested the research, local measurements, changes to OpenJev and its llama.cpp fork, commits with fixed 2026-10-01 dates and the push that publishes them.

Proof: Splash's source read at a pinned commit; measured prefill and cache behaviour on this machine before and after; downloads measured per channel and verified by SHA-256 against pinned revisions; passing builds and HTTP-verified pages.

Likely misfire: porting decode tricks to a one-token workload; claiming Splash runs here when its kernels need Metal 4; a fast mirror that serves different bytes than the pinned revision.
