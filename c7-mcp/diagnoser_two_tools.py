"""Stage 2 of 3 — a SECOND tool, and the straight line BREAKS.

Same code as diagnoser_single_tool.py plus exactly two edits (marked
below): one more entry in TOOLS, one more branch in run_tools. Then ask
the question a real user asks — plan AND hours — and watch it fail.

Run it a few times. The failure wears different clothes (generation is
probabilistic): sometimes the model returns a second decision on pass 2
and final.content is None; sometimes it answers with an ungrounded plan
because the search never ran; sometimes the reply freestyles the very
arithmetic we built a tool for. One thing never varies — read the gate
printed at the end: a two-tool question, and EXACTLY ONE tool executed.

The code assumed exactly one decision. The model gets to make as many
as the question needs, and you cannot know that number in advance.
(The fix: diagnoser.py, where the straight line becomes a loop.)
"""

import json
import os

from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient

# Read GROQ_API_KEY and TAVILY_API_KEY from .env into the environment.
load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

SYSTEM_PROMPT = (
    "You are a workflow diagnosis assistant. ALWAYS use the search_web tool "
    "first, before answering or calling any other tool, to find the current "
    "tools that fit the described workflow. Never do arithmetic yourself; "
    "use a tool for any calculation. Then respond in plain text with "
    "repeatable steps, automation opportunities, and a suggested MVP, "
    "naming specific, current tools."
)


def search_web(query: str) -> dict:
    """Search the web via Tavily (1,000 free credits/month)."""
    return tavily.search(query=query, max_results=5,
                         include_answer=True)


def estimate_time_saved(minutes_per_day: float, days_per_week: int) -> dict:
    """A pure function: arithmetic the model should not freestyle."""
    hours_per_year = minutes_per_day * days_per_week * 52 / 60
    return {"hours_per_year": round(hours_per_year, 1)}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": ("Search the web for current information. ALWAYS "
                            "call this first when diagnosing a workflow: the "
                            "plan must name tools that exist today, and only "
                            "a search can know them."),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string",
                                         "description": "The search query"}},
                "required": ["query"],
            },
        },
    },
    # EDIT ONE OF TWO: the second tool joins the menu the model reads.
    {
        "type": "function",
        "function": {
            "name": "estimate_time_saved",
            "description": ("Convert a task's minutes per day and days per "
                            "week into hours lost per year. Use for any "
                            "time-cost or hours-saved question, after "
                            "search_web has grounded the plan."),
            "parameters": {
                "type": "object",
                "properties": {
                    "minutes_per_day": {
                        "type": "number",
                        "description": "Minutes the task takes each day"},
                    "days_per_week": {
                        "type": "integer",
                        "description": "Days per week the task happens"},
                },
                "required": ["minutes_per_day", "days_per_week"],
            },
        },
    },
]


executed = []   # every tool that actually runs lands here — count them


def run_tools(name: str, args: dict):
    """Execute layer: validate the decision, make the real call."""
    print(f"  [tool call] {name}({args})")
    executed.append(name)
    if name == "search_web":
        return search_web(**args)
    # EDIT TWO OF TWO: one more branch in the routing layer.
    if name == "estimate_time_saved":
        return estimate_time_saved(**args)
    return {"error": f"unknown tool: {name}"}


# ---------------------------------------------------------------------------
# UNCHANGED from diagnoser_single_tool.py — and that is the point.
# This straight line handles exactly one decision. Read the assumption
# in the code: first.tool_calls[0], one execution, one reply.
# ---------------------------------------------------------------------------

def diagnose(workflow_description: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": workflow_description},
    ]

    # Pass 1: the model DECIDES (it cannot execute anything)
    first = client.chat.completions.create(
        model="qwen/qwen3.6-27b", messages=messages,
        tools=TOOLS, tool_choice="auto",
    ).choices[0].message

    # WE execute the decision
    call = first.tool_calls[0]
    args = json.loads(call.function.arguments)
    result = run_tools(call.function.name, args)

    # Pass 2: result goes back in; the model answers, grounded
    messages.append(first)
    messages.append({"role": "tool", "tool_call_id": call.id,
                     "content": json.dumps(result)})
    final = client.chat.completions.create(
        model="qwen/qwen3.6-27b", messages=messages,
        tools=TOOLS,
    ).choices[0].message
    return final.content


if __name__ == "__main__":
    # The question a real user asks: plan AND hours. Two tools are on the
    # menu; the straight line can execute only one decision.
    plan = diagnose(
        "Diagnose my morning routine and name the current tools I should "
        "use: I open Jira, pick a priority task, write a report, and Slack "
        "it to my manager. It takes about 40 minutes a day, 5 days a week. "
        "How many hours a year would automating it save me?"
    )
    print("\n" + str(plan))   # str() so you can SEE it when it's None
    print(f"\n  [the gate] two tools on the menu, {len(executed)} executed: "
          f"{executed} — the straight line permits exactly one decision.")
