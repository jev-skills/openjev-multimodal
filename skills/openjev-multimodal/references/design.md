# Designing decisions for OpenJev

These notes come from building and measuring the Tetris example
(`examples/tetris` in the repository): four Qwen profiles, 60 games, 2,884 decisions
and a design study of nine presentations over the same 48 states.

## Shape the problem

- **Keep rules, arithmetic and execution in code.** Enumerate the legal actions,
  measure what each one does, and press the keys yourself. Ask the model only for the
  judgment between candidates.
- **Decide in larger steps when you can.** A Tetris decision covers the falling piece
  and the next one, so one call replaces two and the model compares complete
  outcomes. The option text is the whole key sequence, which code replays exactly.
- **Prune without weights.** Drop a candidate only when another candidate matches or
  beats it on every measured fact. Two-piece Tetris plans shrink from 300–600 to a
  median of 3 without encoding any preference. When one candidate is left, act
  without calling the model and record the move as forced.
- **Order neutrally.** List options by position, time or name. Never sort by your own
  score: small models favour early labels, and a sorted list lets that bias pass for
  judgment.
- **Keep what never changes in the state.** Send fixed rules and context as the state,
  byte for byte the same on every request, and put what changes in the question.
  OpenJev caches a repeated state, so each request reads only its question: a
  Qwen3.8-27B Tetris decision fell from 1.9 s to 0.7 s.
- **Offer an exit.** Add `none`, `other` or `ask a person` whenever the listed options
  may not cover the situation.

## Write the question

A compact structure that worked well:

```json
{
  "task": "Choose the plan to play: the keys for the falling piece, then for the next piece.",
  "goal": "Clear lines and keep the well healthy for the pieces that follow.",
  "priorities": [
    "Complete rows whenever possible; more rows at once is better.",
    "Do not cover empty cells: new holes are the most expensive mistake.",
    "Keep the stack low and its surface even, so the next pieces fit."
  ],
  "fields": {"clears": "rows completed by the two moves", "new holes": "empty cells sealed under blocks"},
  "image": "One tile per option, lettered like the options: the well after both pieces land."
}
```

Each option then reads as a self-contained line:

```text
J: left left left drop → cols 0-2; then S: drop → cols 3-5. Result: clears 1, new holes 0, height 1
```

- State the facts that decide the choice, in the same order for every option, and
  define each field once in the instructions.
- **Leave out facts the model tends to over-weight.** Showing bumpiness made the 4B
  model trade holes for a flatter surface. In the design runs, removing that one field
  roughly halved its mean regret on the same states (1.95 to 0.99); the image still
  shows the surface shape.
- Rewording alone (holes as words, facts first, strict rules) did not beat a clean
  table of facts. Measure a variant before adopting it.

## Design the image

- **Choose the content first.** Draw what the options will produce, not the whole
  screen. A lettered "outcome sheet" beat a full-board screenshot on every model: for
  the 4B model, regret fell from 0.67 to 0.22 and the median call from 0.94 s to
  0.59 s.
- **Pictures support facts; they do not replace them.** With only the outcome images
  and no facts, regret was 2.4–2.6 for every model, against 0.18–1.44 with both.
- **Match the encoder.** Qwen merges 2 × 2 patches of 16 px into one token, so
  32 px ≈ one token. Drawing one cell per 16 px patch keeps a three-option sheet at
  576 × 128 px and 72 visual tokens. Keep images on the 32 px grid, under the
  1,024 px edge and the 512-token budget, so nothing is resampled.
- **Smaller is often enough.** Halving the sheet changed decisions little and cut
  latency; doubling it added about 150 tokens with no gain. Start small and grow only
  if accuracy improves.
- **Show labels in the picture** with the same letters as the options, and highlight
  what matters (for example, `+1` on a tile that clears a row).
- **The picture matters most for small models.** The 0.8B model cleared 26.6 lines per
  game with the outcome sheet and 13.6 without it, and topped out far less often. The
  4B and 35B models did as well from text alone and answered 140–360 ms faster.

## Measure before you trust it

1. Collect a fixed set of decision states from realistic play.
2. Compare presentations on those exact states: agreement with a reference, the value
   lost when they disagree (regret), and latency.
3. Confirm the winner in end-to-end runs on **fresh seeds** that played no part in the
   design.
4. Report every run, including failures and forced moves, with machine, model,
   quantization and llama.cpp build.

Tetris results on an Apple M3 Max (vision prompt, 5 seeds × 100 pieces):

| Profile | Model | 10 line clears | Lines per game | Agreement | Median call |
| --- | --- | --- | --- | --- | --- |
| fast | Qwen3.5-0.8B Q4_K_M | 5 / 5 | 26.6 | 42% | 0.15 s |
| balanced | Qwen3.5-4B Q4_K_M | 5 / 5 | 35.8 | 73% | 0.65 s |
| quality | Qwen3.6-35B-A3B UD-Q4_K_XL | 5 / 5 | 38.2 | 84% | 0.91 s |
| max | Qwen3.8-27B UD-Q4_K_XL | 5 / 5 | 38.4 | 85% | 4.08 s |

With the compact prompt (rules as a cached state), quality cleared 38.2 lines at 0.14 s
per call and max 38.2 at 0.73 s. Random picks among the same plans clear 14.3.

## Act on the answer

- Execute the top option only when it is clearly ahead; otherwise ask again with more
  context, escalate to a larger profile, or ask a person.
- Keep the whole distribution in your logs. It shows near-ties and systematic
  preferences that the top choice hides.
- Verify the effect of every action in code. In Tetris every key must change the
  state; any other result stops the run instead of falling back silently.
