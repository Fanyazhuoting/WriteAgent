"""World Graph tab — interactive entity relationship graph using pyvis."""
from __future__ import annotations

import html as _html
import tempfile
import requests
import gradio as gr
from pyvis.network import Network

API_BASE = "http://127.0.0.1:8000/api/v1"


def build_graph_html(novel_id: str) -> str:
    if not novel_id:
        return "<p>Start a novel first.</p>"
    try:
        resp = requests.get(f"{API_BASE}/entities/{novel_id}/graph", timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"<p>Error fetching graph: {e}</p>"

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    if not nodes:
        return "<p>No entities in the world state yet. Generate at least one scene.</p>"

    net = Network(height="500px", width="100%", bgcolor="#1a1a2e", font_color="white")
    net.toggle_physics(True)

    color_map = {
        "character": "#e94560",
        "location": "#0f3460",
        "world_rule": "#533483",
        "faction": "#e9a84c",
        "artifact": "#4cc9f0",
    }

    for node in nodes:
        group = node.get("group", "character")
        net.add_node(
            node["id"],
            label=node.get("label", node["id"]),
            color=color_map.get(group, "#888"),
            title=f"Type: {group}",
        )

    for edge in edges:
        net.add_edge(edge["from"], edge["to"], label=edge.get("label", ""))

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        net.save_graph(f.name)
        with open(f.name, encoding="utf-8") as fh:
            raw_html = fh.read()

    # Wrap in iframe so vis.js initialises correctly inside Gradio
    escaped = _html.escape(raw_html)
    return f'<iframe srcdoc="{escaped}" width="100%" height="540px" style="border:none;"></iframe>'


def build_world_graph_tab():
    with gr.Tab("World Graph"):
        gr.Markdown("## Entity Relationship Graph")
        gr.Markdown("Visualizes all characters, locations, factions, and artifacts and their relationships.")

        novel_id_display = gr.Textbox(label="Novel ID", placeholder="Paste your novel ID here")
        refresh_btn = gr.Button("Refresh Graph")
        graph_html = gr.HTML()

        refresh_btn.click(
            fn=build_graph_html,
            inputs=[novel_id_display],
            outputs=[graph_html],
        )
