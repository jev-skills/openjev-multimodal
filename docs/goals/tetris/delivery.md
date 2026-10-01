# Delivery receipt

Published and verified on September 21, 2026. Commit author and committer dates are fixed at October 1, 2026, as for the rest of the history; they are not the measurement dates.

- Skill: [`skills/openjev-multimodal`](../../../skills/openjev-multimodal), installed with `npx openskills install jev-skills/openjev-multimodal/skills/openjev-multimodal -g -y` or `npm run skill:install`
- Example: [`examples/tetris`](../../../examples/tetris) · [test report](../../../examples/tetris/report/README.md)
- Demo page: https://jev-skills.github.io/openjev-multimodal/tetris and https://jev-skills.github.io/openjev-multimodal/zh/tetris
- Browser game and replay: https://jev-skills.github.io/openjev-multimodal/demos/tetris/web/
- Visual report: https://jev-skills.github.io/openjev-multimodal/demos/tetris/report/

## Evidence

Commit `5a117d2` passed the [package workflow](https://github.com/Hand-In/openjev-multimodal/actions/runs/35593282599) and the [documentation deployment](https://github.com/Hand-In/openjev-multimodal/actions/runs/35593282630). The English and Chinese demo pages, the browser game, the visual report, `replays.json`, all three videos, posters and charts returned HTTP 200 with the expected media types; both pages are in the sitemap with language alternates, and `llms.txt` lists the demo. The published replay played a recorded quality game in headless Chrome.

The skill was installed on this Mac from the local folder and from GitHub with OpenSkills; `openskills list` shows its full description and `openskills read` prints it. Its helper script checked health, estimated image tokens (260 for the 640 × 400 checkout image, matching the backend's count) and made real Choice, Noul and Score calls against the local balanced model.

The benchmark ran each profile on its own port with one profile active at a time and the parallel performance session paused: 3 profiles × 5 fresh seeds (101–505) × 2 prompts × 100 pieces, 1,427 decisions, 1,324 model calls and 103 forced moves. Every decision is in `examples/tetris/report/runs/`. The design study (48 fixed states from seeds 1–4, eight presentations) is in `report/ablation/`. The weight files were checked by SHA-256 against the pinned Hugging Face revisions.

`replay.py` and `web/tetris.js` each reproduce all 30 games, every option list and the final scores exactly. Videos are rendered from those replays; their waiting time is the measured round trip of each call. Replay mode, live mode against the 4B model, human play, the Chinese interface and a 390 px phone layout were checked in headless Chrome.

## Results

In vision mode all 15 games reached ten line clears with no illegal key, API error or fallback move. The quality model reached the goal with a hole-free stack in 3 of 5 games (4 of 5 with the text-only prompt). Median decision times were 0.15 s (fast), 0.65 s (balanced) and 0.91 s (quality); agreement with the reference evaluator was 42%, 73% and 84%. The best score after 100 pieces was 15,156 (quality, text-only prompt, seed 101).

## Completion audit

Jev makes every non-forced choice: code only enumerates legal plans, removes plans that are dominated on every measured fact without weights, lists the survivors in position order and presses the chosen keys. The reference evaluator scores decisions afterwards and never selects a move. Image size and content were chosen from measurements: facts plus a 16 px-per-cell outcome sheet gave the lowest regret for every profile; a full-board screenshot and larger images were slower without better decisions; the image mattered most for the 0.8B model.

Five seeds per configuration is a small sample, and timings describe one M3 Max without concurrent load. At 03:39 PDT, after all measurements and videos were complete, the machine restarted from a kernel GPU driver panic triggered by an experiment in a parallel session; no Tetris data came from that run.
