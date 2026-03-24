"""Audit Trail tab — filterable log of all agent calls."""
from __future__ import annotations

import requests
import pandas as pd
import gradio as gr

API_BASE = "http://127.0.0.1:8000/api/v1"


def fetch_audit(novel_id: str, limit: int, from_disk: bool):
    if not novel_id:
        return pd.DataFrame()
    try:
        params = {"limit": limit, "offset": 0, "from_disk": from_disk}
        resp = requests.get(f"{API_BASE}/audit/{novel_id}", params=params, timeout=15)
        resp.raise_for_status()
        entries = resp.json()
        if not entries:
            return pd.DataFrame({"message": ["No audit entries yet."]})
        rows = []
        for e in entries:
            rows.append({
                "Agent": e.get("agent_id", ""),
                "Scene": e.get("scene_number", ""),
                "Timestamp": e.get("timestamp", ""),
                "Prompt Tokens": e.get("prompt_tokens", 0),
                "Completion Tokens": e.get("completion_tokens", 0),
                "Duration (ms)": e.get("duration_ms", 0),
                "Output Preview": e.get("output_preview", "")[:100],
            })
        return pd.DataFrame(rows)
    except Exception as e:
        return pd.DataFrame({"error": [str(e)]})


def build_audit_tab():
    with gr.Tab("Audit Trail"):
        gr.Markdown("## Agent Audit Trail")
        gr.Markdown(
            "Every agent call is logged with timestamp, agent ID, token usage, "
            "and an output preview. Full logs are stored in `audit_logs/<novel_id>.jsonl`."
        )

        with gr.Row():
            novel_id_input = gr.Textbox(label="Novel ID", scale=2)
            limit_slider = gr.Slider(10, 500, value=50, step=10, label="Max Entries", scale=1)
            from_disk_check = gr.Checkbox(label="Read from disk", value=False, scale=1)

        refresh_btn = gr.Button("Refresh Audit Log")
        audit_table = gr.Dataframe(label="Agent Call Log", interactive=False, wrap=True)

        refresh_btn.click(
            fn=fetch_audit,
            inputs=[novel_id_input, limit_slider, from_disk_check],
            outputs=[audit_table],
        )
