"""Vault-mode HTML thumbnail strips + repo-mode plain-text rendering."""
from .action_token import token_view


def render_repo_cell(sig: tuple) -> str:
    """Repo mode: backtick token string, joined with · ."""
    return "`" + " · ".join(sig) + "`" if sig else "(empty turn)"


def render_vault_cell(
    sig: tuple,
    available: set[str],
    assets_dir_rel: str,
    leader_id_for_attack: str | None = None,
    thumb_width: int = 60,
) -> str:
    """Vault mode: two-row HTML table — thumbnails on top, labels below.

    `assets_dir_rel` is the path inside the vault that obsidian resolves
    relative to the rendered markdown file (e.g. `assets/kalgara-vs-teach`).

    `leader_id_for_attack` is the opponent's leader id; used as the thumbnail
    for `attack:LEADER` tokens.
    """
    if not sig:
        return "(empty turn)"
    thumb_cells = []
    label_cells = []
    for tok in sig:
        cid, label = token_view(tok, leader_id=leader_id_for_attack)
        if cid and cid in available:
            thumb_cells.append(
                f'<td><img src="{assets_dir_rel}/{cid}.png" width="{thumb_width}"></td>'
            )
        else:
            thumb_cells.append("<td></td>")
        label_cells.append(f"<td>{label}</td>")
    return (
        "<table><tr>" + "".join(thumb_cells) + "</tr>"
        "<tr>" + "".join(label_cells) + "</tr></table>"
    )


def collect_card_ids_from_sigs(
    sigs: list[tuple],
    extra_ids: set[str] | None = None,
    leader_id_for_attack: str | None = None,
) -> set[str]:
    """Gather every card id referenced by `sigs` for asset bootstrap."""
    ids: set[str] = set(extra_ids or [])
    for sig in sigs:
        for tok in sig:
            cid, _ = token_view(tok, leader_id=leader_id_for_attack)
            if cid:
                ids.add(cid)
    return ids
