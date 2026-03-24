"""
WriteAgent — entry point.

Usage:
    # Start the FastAPI backend
    uvicorn main:app --reload --port 8000

    # Start the Gradio UI (in a separate terminal)
    python -m ui.app
"""
from api.app import app  # noqa: F401 — re-exported for uvicorn

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
