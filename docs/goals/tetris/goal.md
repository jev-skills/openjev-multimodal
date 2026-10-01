# OpenJev agent skill and Tetris demo

1. Following the TypeSafe Jev skill, add an OpenSkills-installable skill for OpenJev Multimodal, written in fluent, professional language, and commit it.
2. Build a Tetris game under `examples/` that the local API plays quickly: moves left, right and rotations, ten line clears without failure, careful image resolution and efficient prompts, a well-designed interaction for Jev (it may predict a sequence of operations), and a visual test report in the example folder.

Later owner requests: test the fast, balanced and quality profiles (latency, best score, lines cleared) with polished charts and tables; record small but clear gameplay videos for each model, animated as a replay of the recorded game with a lean, professional view of every OpenJev call; publish them on GitHub Pages. Commits keep the history's granularity and fixed 2026-10-01 dates.

Authority: the owner requested implementation, local benchmark runs on all three profiles, commits, publication to GitHub Pages and the push that deploys it.

Proof: real runs on every profile with complete decision receipts, a design study on fixed states, fresh benchmark seeds, replays verified against the recordings in Python and JavaScript, rendered videos, a passing docs build and package workflow, HTTP-verified public pages, and a real OpenSkills install from the repository.

Likely misfire: a game where code makes the moves and the model's answer is decorative; screenshots that cost many tokens without improving decisions; seeds reused from prompt design; videos that fake the model's timing.
