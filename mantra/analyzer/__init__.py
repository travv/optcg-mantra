"""Reusable building blocks for Mantra replay analyses.

The kernel that the `example-analysis/` scripts share. Originally extracted
from `example-analysis/kalgara-vs-teach-5don-turns.py` so multiple analyses
can reuse the same action-token logic, rendering, and asset bootstrap.

Modules:

- `replay_loader` — load parsed JSONs from a matchup folder; player↔leader helpers.
- `decklist`     — parse the `_metadata.winner_deck` / `_metadata.loser_deck` strings.
- `matchup_lookup` — locate matchup folders under `$MANTRA_VAULT_ROOT`.
- `action_token` — verb-aware action -> compact-token serializer; main/existing-board split.
- `assets`       — card-art download + local cache.
- `render`       — vault-mode HTML thumbnail strips + repo-mode plain text.

See `example-analysis/` for end-to-end usage.
"""
