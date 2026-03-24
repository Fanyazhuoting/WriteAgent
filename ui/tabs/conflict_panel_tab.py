"""Conflict Panel tab — real-time agent negotiation visualization."""
from __future__ import annotations

import requests
import pandas as pd
import gradio as gr

API_BASE = "http://127.0.0.1:8000/api/v1"


def fetch_negotiations(novel_id: str):
    if not novel_id:
        return pd.DataFrame()
    try:
        resp = requests.get(f"{API_BASE}/audit/{novel_id}/negotiations", timeout=10)
        resp.raise_for_status()
        rounds = resp.json()
        if not rounds:
            return pd.DataFrame({"message": ["No negotiations recorded yet."]})
        rows = []
        for r in rounds:
            rows.append({
                "Round": r.get("round_number", ""),
                "Participants": ", ".join(r.get("participants", [])),
                "Proposal (preview)": r.get("proposal", "")[:120] + "...",
                "Resolution": r.get("resolution", ""),
                "Resolved": "✅" if r.get("resolved") else "❌",
                "Timestamp": r.get("timestamp", ""),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        return pd.DataFrame({"error": [str(e)]})


def build_conflict_panel_tab():
    with gr.Tab("Conflict Panel"):
        gr.Markdown("## Agent Negotiation Log")
        gr.Markdown(
            "When the Consistency Checker detects a contradiction, "
            "agents negotiate a resolution. All rounds are logged here."
        )

        novel_id_input = gr.Textbox(label="Novel ID")
        refresh_btn = gr.Button("Refresh Negotiations")
        negotiation_table = gr.Dataframe(
            label="Negotiation Rounds",
            interactive=False,
            wrap=True,
        )

        refresh_btn.click(
            fn=fetch_negotiations,
            inputs=[novel_id_input],
            outputs=[negotiation_table],
        )
