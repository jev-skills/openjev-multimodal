# Qwen3.8-27B as the `max` profile

Research whether a locally deployable Qwen 3.8 model (a 27B class) can meet the Tetris latency requirement of about one second per decision. Add it as the profile with the highest capability, change the inference or readout layer where needed, and report its Tetris results. The llama.cpp fork lives in `.llamacpp/` (ignored by Git); modify it for performance and robustness. Compare the published 8-bit, MLX and MTP variants and choose the one that performs best with image input.

Earlier requests carried into this round: publish the latency work on main; add no-model baselines to the Tetris report and make clear that code simulates and the model chooses; keep the site Apple-like, minimal and free of filler.

Authority: the owner requested the research, downloads in the background, local benchmark runs, changes to OpenJev and the local llama.cpp fork, commits with fixed 2026-10-01 dates and the push that publishes them.

Proof: pinned weights; latency measured on this machine with one model on the GPU at a time; Tetris receipts for every profile and prompt; decisions checked against stock llama.cpp; replays verified in Python and JavaScript; passing builds and HTTP-verified pages.

Likely misfire: a sub-second number from a prompt that hides work in a warm cache nobody else would have; a patch that changes answers; claiming a model judges better than the data shows; running MLX or a second model beside another GPU workload after the kernel panic.
