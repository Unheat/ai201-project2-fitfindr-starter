"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq
from config import MATCHING_THRESHOLD, GROQ_API_KEY, LLM_MODEL, TEMPERATURE
from utils.data_loader import load_listings
load_dotenv()
_client = Groq(api_key=GROQ_API_KEY)

# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    

    TODO:
        1. Load all listings with load_listings().
        2. Filter by max_price and size (if provided).
        3. Score each remaining listing by keyword overlap with `description`.
        4. Drop any listings with a score of 0 (no relevant matches).
        5. Sort by score, highest first, and return the listing dicts.

    Before writing code, fill in the Tool 1 section of planning.md.
    """
# 1. Tokenize into words safely
    query_tokens = description.lower().split()
    
    # Edge case: If user passed an empty description, return empty list
    if not query_tokens:
        return []
        
    scored_results = []
    items = load_listings()
    
    # Define your strictness (e.g., 50% of the query words must match)
    required_matches = len(query_tokens) * MATCHING_THRESHOLD
    
    for item in items:
        # Price and Size Filtering
        if max_price is not None and item.get("price", float('inf')) > max_price:
            continue
        if size is not None:
            if size.lower() not in item.get("size", "").lower():
                continue
        
        # Safe extraction and flattening
        title = item.get("title", "")
        item_desc = item.get("description", "")
        category = item.get("category", "")
        colors_str = " ".join(item.get("colors", []))
        tags_str = " ".join(item.get("style_tags", []))
        
        searchable_text = f"{title} {item_desc} {category} {colors_str} {tags_str}".lower()
        
        # 2. Your threshold logic: Check how many words matched
        matched_words = [word for word in query_tokens if word in searchable_text]
        score = len(matched_words)
        
        # 3. Apply the threshold to drop weak matches
        if score >= required_matches:
            scored_results.append((score, item))
    # handle no match case
    if len(scored_results) == 0:
        return scored_results # return empty list
            
    # 4. Sort so the best possible matches are at the top for the LLM
    scored_results.sort(key=lambda x: x[0], reverse=True)
    
    # Return just the dictionaries
    return [res[1] for res in scored_results]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying). {title: "...", description: "..."}
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.

    TODO:
        1. Check whether wardrobe['items'] is empty.
        2. If empty: call the LLM with a prompt for general styling ideas
           (what kinds of items pair well, what vibe it suits, etc.).
        3. If not empty: format the wardrobe items into a prompt and ask
           the LLM to suggest specific outfit combinations using the new item
           and named pieces from the wardrobe.
        4. Return the LLM's response as a string.

    Before writing code, fill in the Tool 2 section of planning.md.
    """
    # Replace this with your implementation
    owned_items = wardrobe.get("items", [])
    item_context = f"{new_item.get('title', 'Unknown')} - {new_item.get('description', '')}"
    if not owned_items:
        system_prompt = (
            "You are an expert fashion stylist. The user wants to build an outfit "
            "around a new thrifted item, but their saved wardrobe is currently empty. "
            "Suggest 1-2 complete outfits pairing the new item with universal, accessible basic clothing "
            "(e.g., standard blue jeans, plain white tee, neutral sneakers). "
            "Briefly acknowledge that you are suggesting basics to build around their new piece."
        )
        user_prompt = f"Design an outfit for this new item:\n{item_context}"
        
    else:
        wardrobe_list = "\n".join([
            f"- {item.get('name', 'Unknown')} ({item.get('category', 'Category')}): "
            f"Colors: {', '.join(item.get('colors', []))}, "
            f"Tags: {', '.join(item.get('style_tags', []))}, "
            f"Notes: {item.get('notes', 'None')} " 
            for item in owned_items
        ])
        system_prompt = (
            "You are an expert fashion stylist. The user wants to build an outfit "
            "combining a new thrifted item with clothes they already own. "
            "CRITICAL SYSTEM RULE: You MUST ONLY suggest pairing the new item with the clothes "
            "explicitly listed in their wardrobe. Do not hallucinate or suggest items they do not own."
        )
        user_prompt = f"New Item:\n{item_context}\n\nUser's Wardrobe:\n{wardrobe_list}\n\nDesign 1-2 outfits."
    try:
        response = _client.chat.completions.create(
            model = LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=TEMPERATURE
        )
        return response.choices[0].message.content
    except Exception as e:
        # Graceful degradation if the API fails
        return "I'm having trouble connecting to my styling engine right now. Please try again later."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)

    TODO:
        1. Guard against an empty or whitespace-only outfit string.
        2. Build a prompt that gives the LLM the item details and the outfit,
           and asks for a caption matching the style guidelines above.
        3. Call the LLM and return the response.

    Before writing code, fill in the Tool 3 section of planning.md.
    """
    if not outfit or not outfit.strip():
        return "I'm having trouble connecting to my styling engine right now. Please try again later."
    item_context = f"{new_item.get('title', 'Unknown')} - {new_item.get('description', '')}"

    system_prompt = (
    f"""
    Generate a short, shareable outfit caption for the thrifted find base on the outfit we recommended to user previously and the new item user just bought.
    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    """
    )
    user_prompt = f"give me a short, shareable outfit caption for the thrifted find. New item I just bought: {item_context} Previous suggestion: {outfit}"
    try:
        response = _client.chat.completions.create(
            model = LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=TEMPERATURE
        )
        return response.choices[0].message.content
    except Exception as e:
        # Graceful degradation if the API fails
        return "I'm having trouble connecting to my styling engine right now. Please try again later. "