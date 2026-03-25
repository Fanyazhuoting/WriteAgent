"""Writer tab — main writing interface with human-in-the-loop injection."""
from __future__ import annotations

import time
import requests
import gradio as gr

API_BASE = "http://127.0.0.1:8000/api/v1"
POLL_INTERVAL = 3      # seconds between status polls
POLL_TIMEOUT  = 600    # max seconds to wait for generation


def start_novel(genre: str, style_guide: str, first_scene_brief: str,
                characters_raw: str, rules_raw: str):
    """POST /novel/start and return novel_id + status message."""
    initial_chars = []
    for line in characters_raw.strip().splitlines():
        if ":" in line:
            name, desc = line.split(":", 1)
            initial_chars.append({"name": name.strip(), "description": desc.strip()})
        elif line.strip():
            initial_chars.append({"name": line.strip(), "description": line.strip()})

    initial_rules = []
    for line in rules_raw.strip().splitlines():
        if line.strip():
            parts = line.split("|")
            rule = {"description": parts[0].strip()}
            if len(parts) > 1:
                rule["severity"] = parts[1].strip()
            if len(parts) > 2:
                rule["category"] = parts[2].strip()
            initial_rules.append(rule)

    payload = {
        "genre": genre,
        "style_guide": style_guide,
        "first_scene_brief": first_scene_brief,
        "initial_characters": initial_chars,
        "initial_world_rules": initial_rules,
    }
    try:
        resp = requests.post(f"{API_BASE}/novel/start", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        return data["novel_id"], f"Novel started! ID: {data['novel_id']}"
    except Exception as e:
        return "", f"Error: {e}"


def generate_scene(novel_id: str, scene_brief: str, prose_so_far: str):
    """
    POST /scene/next (returns immediately), then poll /scene/generation_status
    until done or error.
    """
    if not novel_id:
        return prose_so_far, "Please start a novel first."

    # 1. Kick off generation
    try:
        resp = requests.post(
            f"{API_BASE}/novel/{novel_id}/scene/next",
            json={"scene_brief": scene_brief},
            timeout=30,
        )
        resp.raise_for_status()
    except Exception as e:
        return prose_so_far, f"Error starting generation: {e}"

    # 2. Poll for completion
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(POLL_INTERVAL)
        try:
            poll = requests.get(
                f"{API_BASE}/novel/{novel_id}/scene/generation_status",
                timeout=10,
            )
            poll.raise_for_status()
            job = poll.json()
        except Exception as e:
            return prose_so_far, f"Error polling status: {e}"

        status = job.get("status")

        if status == "error":
            return prose_so_far, f"Generation error: {job.get('error', 'unknown')}"

        if status == "done":
            data = job["result"]
            prose = data.get("final_prose", "")
            stats = (
                f"Scene {data['scene_number']} done | "
                f"Contradictions: {data['contradictions_found']} | "
                f"Negotiations: {data['negotiation_rounds']} | "
                f"Resolved: {data.get('negotiation_resolved', False)}"
            )
            separator = f"\n\n{'─' * 60}\n\n"
            new_prose = prose_so_far + separator + prose if prose_so_far else prose
            return new_prose, stats

        # status == "generating" → keep polling

    return prose_so_far, "Timed out waiting for generation (>10 min). Check backend logs."


def inject_event(novel_id: str, event_text: str, next_brief: str):
    if not novel_id:
        return "Please start a novel first."
    try:
        payload = {"event": event_text}
        if next_brief:
            payload["next_scene_brief"] = next_brief
        resp = requests.post(f"{API_BASE}/novel/{novel_id}/inject", json=payload, timeout=30)
        resp.raise_for_status()
        return f"Event injected: {event_text[:80]}..."
    except Exception as e:
        return f"Error: {e}"


def build_writer_tab():
    with gr.Tab("Writer"):
        gr.Markdown("## Novel Configuration")
        with gr.Row():
            genre_input = gr.Textbox(label="Genre", value="Fantasy", scale=1)
            style_input = gr.Textbox(
                label="Style Guide",
                value="Third-person limited, literary fiction",
                scale=2,
            )

        first_brief = gr.Textbox(
            label="First Scene Brief",
            placeholder="e.g. Elena discovers an ancient map in her grandmother's attic...",
            lines=2,
        )
        with gr.Row():
            chars_input = gr.Textbox(
                label="Initial Characters (name: description, one per line)",
                placeholder="Elena: A curious young archivist\nMarcus: A gruff but loyal blacksmith",
                lines=4,
                scale=1,
            )
            rules_input = gr.Textbox(
                label="World Rules (description | severity | category, one per line)",
                placeholder="Magic requires rare crystals | absolute | magic\nNo firearms exist | absolute | physics",
                lines=4,
                scale=1,
            )

        start_btn = gr.Button("Start Novel", variant="primary")
        novel_id_state = gr.State("")
        status_box = gr.Textbox(label="Status", interactive=False)

        gr.Markdown("---")
        gr.Markdown("## Scene Generation")
        scene_brief_input = gr.Textbox(
            label="Next Scene Brief",
            placeholder="Elena follows the map into the Silvermere Forest...",
            lines=2,
        )
        generate_btn = gr.Button("Generate Scene", variant="primary")
        stats_box = gr.Textbox(
            label="Scene Stats (polls every 3s until done)",
            interactive=False,
        )

        prose_output = gr.Textbox(
            label="Novel Prose",
            lines=25,
            interactive=False,
        )

        gr.Markdown("---")
        gr.Markdown("## Human-in-the-Loop Event Injection")
        with gr.Row():
            inject_text = gr.Textbox(label="Plot Event to Inject", lines=2, scale=2)
            inject_brief = gr.Textbox(label="Next Scene Brief (optional)", lines=2, scale=1)
        inject_btn = gr.Button("Inject Event")
        inject_status = gr.Textbox(label="Injection Status", interactive=False)

        # Wire up events
        start_btn.click(
            fn=start_novel,
            inputs=[genre_input, style_input, first_brief, chars_input, rules_input],
            outputs=[novel_id_state, status_box],
        )
        generate_btn.click(
            fn=generate_scene,
            inputs=[novel_id_state, scene_brief_input, prose_output],
            outputs=[prose_output, stats_box],
        )
        inject_btn.click(
            fn=inject_event,
            inputs=[novel_id_state, inject_text, inject_brief],
            outputs=[inject_status],
        )
