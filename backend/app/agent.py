import json
import os
import time
from typing import Any, Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from app.tools.search_parts import search_parts
from app.tools.get_part_details import get_part_details
from app.tools.check_compatibility import check_compatibility
from app.tools.troubleshoot import troubleshoot

load_dotenv()

_client: Optional[genai.Client] = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client

MODEL = "gemini-2.5-flash"
MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """You are PartSelect's helpful parts assistant, specializing ONLY in refrigerator and dishwasher replacement parts.

Your capabilities:
- Help users find the right part for their appliance
- Provide installation instructions and part details
- Check whether a part is compatible with a specific model number
- Diagnose common appliance problems and suggest likely replacement parts
- Answer questions about pricing, availability, and part specifications

Your limitations:
- You ONLY help with refrigerator and dishwasher parts. Politely decline any other topics.
- Never make up part numbers, prices, or compatibility data. Always use your tools.
- If you cannot find information with your tools, say so honestly.

Tone: friendly, knowledgeable, concise. Use bullet points for lists. Be specific with part numbers.

When presenting parts, always include the part number, title, and price if available."""

TOOL_DECLARATIONS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="search_parts",
        description=(
            "Search the parts catalog for refrigerator or dishwasher parts matching "
            "a natural-language query (e.g. 'ice maker assembly', 'dishwasher door latch'). "
            "Returns a ranked list of matching parts with part numbers, titles, prices, and images."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="Natural language description of the part or problem",
                ),
                "appliance_type": types.Schema(
                    type=types.Type.STRING,
                    description="Filter by appliance type: 'refrigerator', 'dishwasher', or '' for any",
                ),
                "n_results": types.Schema(
                    type=types.Type.INTEGER,
                    description="Number of results to return (default 5, max 8)",
                ),
            },
            required=["query"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_part_details",
        description=(
            "Retrieve complete details for a specific part by its part number "
            "(e.g. PS11752778). Returns description, installation info, compatibility list, and price."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "part_number": types.Schema(
                    type=types.Type.STRING,
                    description="The PartSelect part number (e.g. PS11752778)",
                ),
            },
            required=["part_number"],
        ),
    ),
    types.FunctionDeclaration(
        name="check_compatibility",
        description=(
            "Check whether a specific part is compatible with an appliance model number. "
            "Use this when the user asks 'is this part compatible with my [model]?'"
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "model_number": types.Schema(
                    type=types.Type.STRING,
                    description="The appliance model number (e.g. WDT780SAEM1)",
                ),
                "part_number": types.Schema(
                    type=types.Type.STRING,
                    description="The PartSelect part number to check (e.g. PS11752778)",
                ),
            },
            required=["model_number", "part_number"],
        ),
    ),
    types.FunctionDeclaration(
        name="troubleshoot",
        description=(
            "Search repair guides and troubleshooting articles for a described symptom "
            "(e.g. 'ice maker not making ice', 'dishwasher not draining'). "
            "Returns relevant repair guide excerpts and likely causes."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "symptom": types.Schema(
                    type=types.Type.STRING,
                    description="Description of the problem or symptom",
                ),
                "appliance_type": types.Schema(
                    type=types.Type.STRING,
                    description="Filter by appliance type: 'refrigerator', 'dishwasher', or '' for any",
                ),
            },
            required=["symptom"],
        ),
    ),
])


def _send_with_retry(chat, message, max_attempts: int = 4):
    for attempt in range(max_attempts):
        try:
            return chat.send_message(message)
        except Exception as e:
            err = str(e)
            is_last = attempt == max_attempts - 1
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                if is_last:
                    raise
                wait = 65 if attempt >= 1 else 20
                print(f"  [rate limit] waiting {wait}s (attempt {attempt+1}/{max_attempts})...")
                time.sleep(wait)
            elif "503" in err or "UNAVAILABLE" in err:
                if is_last:
                    raise
                time.sleep((attempt + 1) * 5)
            else:
                raise


def _run_tool(name: str, args: dict) -> Any:
    if name == "search_parts":
        return search_parts(
            query=args["query"],
            appliance_type=args.get("appliance_type", ""),
            n_results=args.get("n_results", 5),
        )
    if name == "get_part_details":
        result = get_part_details(args["part_number"])
        return result if result else {"error": f"Part {args['part_number']} not found."}
    if name == "check_compatibility":
        return check_compatibility(
            model_number=args["model_number"],
            part_number=args["part_number"],
        )
    if name == "troubleshoot":
        return troubleshoot(
            symptom=args["symptom"],
            appliance_type=args.get("appliance_type", ""),
        )
    return {"error": f"Unknown tool: {name}"}


def _extract_products(tool_results: list[dict]) -> list[dict]:
    """Collect product cards from all tool results, deduplicating by part number."""
    products: list[dict] = []
    seen: set[str] = set()
    for result in tool_results:
        data = result.get("data")
        if isinstance(data, list):
            for item in data:
                pn = item.get("part_number", "")
                if pn and pn not in seen and item.get("title"):
                    seen.add(pn)
                    products.append({
                        "part_number": pn,
                        "title": item.get("title", ""),
                        "price": item.get("price", ""),
                        "image_url": item.get("image_url", ""),
                        "url": item.get("url", ""),
                        "appliance_type": item.get("appliance_type", ""),
                    })
        elif isinstance(data, dict) and data.get("part_number") and data.get("title"):
            pn = data["part_number"]
            if pn not in seen:
                seen.add(pn)
                products.append({
                    "part_number": pn,
                    "title": data.get("title", ""),
                    "price": data.get("price", ""),
                    "image_url": data.get("image_url", ""),
                    "url": data.get("url", ""),
                    "appliance_type": data.get("appliance_type", ""),
                })
    return products


def _to_gemini_history(messages: list[dict]) -> list[types.Content]:
    history = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        history.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))
    return history


def run_agent(messages: list[dict]) -> dict:
    client = _get_client()
    tool_results_accumulator: list[dict] = []

    history = _to_gemini_history(messages[:-1])
    current_message = messages[-1]["content"]

    chat = client.chats.create(
        model=MODEL,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[TOOL_DECLARATIONS],
            temperature=0.2,  # low temperature keeps part numbers and prices factual
        ),
        history=history,
    )

    response = _send_with_retry(chat, current_message)

    for _ in range(MAX_TOOL_ROUNDS):
        fn_calls = [p.function_call for p in response.candidates[0].content.parts
                    if p.function_call is not None]

        if not fn_calls:
            text = "".join(
                p.text for p in response.candidates[0].content.parts
                if hasattr(p, "text") and p.text
            )
            products = _extract_products(tool_results_accumulator)
            return {"role": "assistant", "content": text, "products": products}

        fn_response_parts = []
        for fn_call in fn_calls:
            args = dict(fn_call.args) if fn_call.args else {}
            raw_result = _run_tool(fn_call.name, args)
            tool_results_accumulator.append({"tool": fn_call.name, "data": raw_result})
            fn_response_parts.append(
                types.Part.from_function_response(
                    name=fn_call.name,
                    response={"result": raw_result},
                )
            )

        response = _send_with_retry(chat, fn_response_parts)

    text = "".join(
        p.text for p in response.candidates[0].content.parts
        if hasattr(p, "text") and p.text
    )
    return {
        "role": "assistant",
        "content": text or "I'm sorry, I wasn't able to complete that request.",
        "products": _extract_products(tool_results_accumulator),
    }
