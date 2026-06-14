"""
app.py

Gradio interface for FitFindr. The layout and wiring are already set up —
your job is to fill in handle_query() so it calls run_agent() and maps
the session results to the three output panels.

Run with:
    python app.py

Then open the localhost URL shown in your terminal (usually http://localhost:7860,
but check your terminal — the port may differ).
"""

import gradio as gr

from agent import run_agent
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query handler ─────────────────────────────────────────────────────────────

def handle_query(user_query: str, wardrobe_choice: str, chat_history=None) -> tuple[str, str, str, list, list]:
    """
    Called by Gradio when the user submits a query.
    Args:
        user_query:     The text the user typed into the search box.
        wardrobe_choice: Either "Example wardrobe" or "Empty wardrobe (new user)".
        chat_history:  The list of messages from previous interactions in this session.
    Returns:
        A tuple of four values:
            (listing_text, outfit_suggestion, fit_card, updated_chat_history)
    """
    chat_messages = list(chat_history or [])

    if not user_query or not user_query.strip():
        return "Please enter what you are looking for first.", "", "", chat_messages, chat_messages

    if wardrobe_choice == "Example wardrobe":
        wardrobe = get_example_wardrobe()
    else:
        wardrobe = get_empty_wardrobe()

    session = run_agent(user_query, wardrobe, chat_messages)

    if session.get("error"):
        chat_messages.append({"role": "user", "content": user_query})
        chat_messages.append({"role": "assistant", "content": session["error"]})
        return session["error"], "", "", chat_messages, chat_messages

    selected_item = session.get("selected_item") or {}
    listing_text = "\n".join(
        [
            f"Title: {selected_item.get('title', 'Unknown item')}",
            f"Price: ${selected_item.get('price', 'n/a')}",
            f"Size: {selected_item.get('size', 'n/a')}",
            f"Condition: {selected_item.get('condition', 'n/a')}",
            f"Platform: {selected_item.get('platform', 'n/a')}",
            f"Description: {selected_item.get('description', 'No description available.')}",
        ]
    )

    chat_messages.append({"role": "user", "content": user_query})
    chat_messages.append({"role": "assistant", "content": session.get("final_reply") or "FitFindr finished the search and styling flow."})

    return (
        listing_text,
        session.get("outfit_suggestion", ""),
        session.get("fit_card", ""),
        chat_messages,
        chat_messages,
    )


# ── interface ─────────────────────────────────────────────────────────────────

EXAMPLE_QUERIES = [
    "vintage graphic tee under $30",
    "90s track jacket in size M",
    "flowy midi skirt under $40",
    "black combat boots size 8",
    "designer ballgown size XXS under $5",   # deliberate no-results test
]

def build_interface():
    with gr.Blocks(title="FitFindr") as demo:
        chat_history = gr.State([])

        gr.Markdown("""
# FitFindr 🛍️
Find secondhand pieces and get outfit ideas based on your wardrobe.
Describe what you're looking for — include size and price if you want to filter.
        """)

        with gr.Row():
            query_input = gr.Textbox(
                label="What are you looking for?",
                placeholder="e.g. vintage graphic tee under $30, size M",
                lines=2,
                scale=3,
            )
            wardrobe_choice = gr.Radio(
                choices=["Example wardrobe", "Empty wardrobe (new user)"],
                value="Example wardrobe",
                label="Wardrobe",
                scale=1,
            )

        submit_btn = gr.Button("Find it", variant="primary")

        chatbot = gr.Chatbot(label="Conversation history", height=220)

        with gr.Row():
            listing_output = gr.Textbox(
                label="🛍️ Top listing found",
                lines=8,
                interactive=False,
            )
            outfit_output = gr.Textbox(
                label="👗 Outfit idea",
                lines=8,
                interactive=False,
            )
            fitcard_output = gr.Textbox(
                label="✨ Your fit card",
                lines=8,
                interactive=False,
            )

        gr.Examples(
            examples=[[q, "Example wardrobe"] for q in EXAMPLE_QUERIES],
            inputs=[query_input, wardrobe_choice],
            label="Try these queries",
        )

        submit_btn.click(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, chat_history],
            outputs=[listing_output, outfit_output, fitcard_output, chat_history, chatbot],
        )
        query_input.submit(
            fn=handle_query,
            inputs=[query_input, wardrobe_choice, chat_history],
            outputs=[listing_output, outfit_output, fitcard_output, chat_history, chatbot],
        )

    return demo


if __name__ == "__main__":
    demo = build_interface()
    demo.launch()
