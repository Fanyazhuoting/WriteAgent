"""Gradio multi-tab UI entry point."""
import gradio as gr

from ui.tabs.writer_tab import build_writer_tab
from ui.tabs.world_graph_tab import build_world_graph_tab
from ui.tabs.conflict_panel_tab import build_conflict_panel_tab
from ui.tabs.audit_tab import build_audit_tab


def create_ui() -> gr.Blocks:
    with gr.Blocks(
        title="WriteAgent — Multi-Agent Novel Writer",
        theme=gr.themes.Soft(),
    ) as demo:
        gr.Markdown(
            "# WriteAgent\n"
            "**Multi-agent AI novel writing system** powered by Qwen-max, LangGraph, and ChromaDB."
        )

        build_writer_tab()
        build_world_graph_tab()
        build_conflict_panel_tab()
        build_audit_tab()

    return demo


if __name__ == "__main__":
    ui = create_ui()
    ui.launch(server_name="0.0.0.0", server_port=7860, share=False)
