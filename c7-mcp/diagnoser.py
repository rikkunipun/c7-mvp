"""Stage 3 of 3 — THE LOOP. Repeat until the model stops deciding.

Name what the straight line really was: decide, execute, respond, ONCE.
The fix is not new machinery; it is repetition with an exit: repeat
until the model stops deciding and answers. That is a while loop with
one exit condition — no tool calls.

Same tools, same contract, same prompt as diagnoser_two_tools.py. Only
diagnose() changed. Re-run the two-tool question that broke the straight
line and read the trace: search fires, estimate_time_saved fires with
the extracted numbers, then no tool call — the model weaves the grounded
plan and 173.3 hours into one reply. This file is what server.py serves.
"""

import json
import os

from dotenv import load_dotenv
from groq import Groq
from tavily import TavilyClient

# Read GROQ_API_KEY and TAVILY_API_KEY from .env into the environment.
# (On FastMCP Cloud these come from the project settings instead.)
load_dotenv()

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
tavily = TavilyClient(api_key=os.environ.get("TAVILY_API_KEY"))

import tiktoken

def count_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

def extract_keywords(text: str) -> set[str]:
    stopwords = {"i", "a", "an", "the", "to", "and", "it", "my", "for", "of",
                 "in", "on", "is", "this", "that", "at", "would", "how",
                 "me", "you", "your", "check", "diagnose"}
    words = text.lower().replace(",", " ").replace(".", " ").replace("—", " ").split()
    return {w for w in words if w not in stopwords and len(w) > 2}

def filter_relevant(items: list[dict], get_text, keywords: set[str], top_n: int) -> list[dict]:
    scored = []
    for item in items:
        text = get_text(item).lower()
        count = 0
        for kw in keywords:
            if kw in text:
                count = count + 1
        if count == 0:
            continue
        scored.append((count, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top_items = []
    for pair in scored[:top_n]:
        top_items.append(pair[1])
    return top_items


def calendar_event_text(event: dict) -> str:
    return event["title"] + " " + event["description"]


def search_result_text(result: dict) -> str:
    return result["title"] + " " + result["content"]



MOCK_CALENDAR_EVENTS = [
    {"title": "1:1 with Manager", "date": "2026-08-03",
     "start_time": "09:00", "end_time": "09:30",
     "attendees": ["You", "Priya (Manager)"],
     "description": "Weekly sync: Jira priority tasks, status report, blockers."},
    {"title": "Sprint Planning", "date": "2026-08-03",
     "start_time": "10:00", "end_time": "11:00",
     "attendees": ["You", "Priya (Manager)", "Dev Team"],
     "description": "Plan Jira backlog for the upcoming sprint, assign priority tickets."},
    {"title": "Dentist Appointment", "date": "2026-08-03",
     "start_time": "14:00", "end_time": "15:00",
     "attendees": ["You"],
     "description": "Routine checkup and cleaning."},
    {"title": "Design Team Standup", "date": "2026-08-04",
     "start_time": "09:30", "end_time": "09:45",
     "attendees": ["Design Team"],
     "description": "Daily standup for the design team's ongoing UI revamp."},
    {"title": "Jira Backlog Grooming", "date": "2026-08-04",
     "start_time": "11:00", "end_time": "12:00",
     "attendees": ["You", "Priya (Manager)"],
     "description": "Review and re-prioritize open Jira tickets, update status."},
    {"title": "Marketing All-Hands", "date": "2026-08-04",
     "start_time": "15:00", "end_time": "16:00",
     "attendees": ["Marketing Team"],
     "description": "Quarterly marketing roadmap review."},
    {"title": "Lunch with College Friend", "date": "2026-08-05",
     "start_time": "12:30", "end_time": "13:30",
     "attendees": ["You", "Alex"],
     "description": "Catch-up lunch, no work topics."},
    {"title": "Weekly Status Report Sync", "date": "2026-08-05",
     "start_time": "16:00", "end_time": "16:30",
     "attendees": ["You", "Priya (Manager)"],
     "description": "Slack report review: today's Jira task summary before sending to manager."},
    {"title": "Sprint Retrospective", "date": "2026-08-06",
     "start_time": "10:00", "end_time": "11:00",
     "attendees": ["You", "Priya (Manager)", "Dev Team"],
     "description": "Retro on the last sprint's Jira ticket throughput and blockers."},
    {"title": "1:1 with Manager", "date": "2026-08-07",
     "start_time": "09:00", "end_time": "09:30",
     "attendees": ["You", "Priya (Manager)"],
     "description": "Weekly sync: Jira priority tasks, status report, blockers."},

]


SYSTEM_PROMPT = (
    "You are a workflow diagnosis assistant. ALWAYS use the search_web tool "
    "first, before answering or calling any other tool, to find the current "
    "tools that fit the described workflow. Never do arithmetic yourself; "
    "use a tool for any calculation. Then respond in plain text with "
    "repeatable steps, automation opportunities, and a suggested MVP, "
    "naming specific, current tools."
    "If the workflow is related to a calendar event, always use the get_calendar_events tool to get the current calendar events to avoid scheduling conflicts. "
    "If date range isn't given in the user description, ask a follow-up question."
)


def search_web(query: str) -> dict:
    """Search the web via Tavily (1,000 free credits/month)."""
    return tavily.search(query=query, max_results=8,
                         include_answer=True)

def get_calendar_events(start_date: str, end_date: str) -> dict:
    """Return calendar events in a date range (mock data)."""
    # Return the whole mock week regardless of dates for now —
    # date filtering comes later. Bulk first, correctness later.
    return {"events": MOCK_CALENDAR_EVENTS}
                    


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
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": (
                "So this tool does fetch calendar events for the date range And this model should reach when the workflow involves meeting/ scheduling And this needs start_date and end_date, If this is not given in the user description, the model should not guess them.."  # when to call this, and that it needs a date range
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string",
                                   "description": "Start of range, YYYY-MM-DD"},
                    "end_date": {"type": "string",
                                 "description": "End of range, YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
]

def run_tools(name: str, args: dict, workflow_description: str):
    print(f"  [tool call] {name}({args})")
    keywords = extract_keywords(workflow_description)
    if name == "search_web":
        raw = search_web(**args)
        raw["results"] = filter_relevant(raw["results"], search_result_text, keywords, top_n=5)
        return raw

    if name == "estimate_time_saved":
        return estimate_time_saved(**args)
    if name == "get_calendar_events":
        raw = get_calendar_events(**args)
        raw["events"] = filter_relevant(raw["events"], calendar_event_text, keywords, top_n=5)
        return raw
    return {"error": f"unknown tool: {name}"}





# ---------------------------------------------------------------------------
# The loop. The same routing decision made repeatedly, each result changing
# the next decision. Every pass, the model re-reads the whole tool menu —
# which is why descriptions matter more as tools multiply.
# ---------------------------------------------------------------------------

def diagnose(workflow_description: str) -> str:
    open("raw_tool_output.json", "w").close()  # start each run with a clean file
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": workflow_description},
    ]
    while True:
        print(f"Token count: {count_tokens(json.dumps(messages))}")
        msg = client.chat.completions.create(
            model="qwen/qwen3.6-27b", messages=messages,
            tools=TOOLS, tool_choice="auto",
        ).choices[0].message

        if not msg.tool_calls:      # the model answered: done
            return msg.content

        messages.append(msg.model_dump(exclude_none=True))        # keep the decision in history
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments)
            result = run_tools(call.function.name, args, workflow_description)  # WE execute
            print(f"Tool result token count: {count_tokens(json.dumps(result))}")
            with open("raw_tool_output.json", "a") as f:
                f.write(f"=== {call.function.name}({args}) ===\n")
                f.write(json.dumps(result, indent=2))
                f.write("\n\n")
            messages.append({"role": "tool",
                             "tool_call_id": call.id,
                             "content": json.dumps(result)})


if __name__ == "__main__":
    # The question that broke the straight line. Nothing else changed —
    # the while was already enough.
    plan = diagnose(
        "I open Jira, pick a priority task, write a status report, and Slack "
        "it to my manager every morning — it takes 40 minutes a day, 5 days "
        "a week. Diagnose this workflow, check my calendar between "
        "2026-08-03 and 2026-08-07 for meetings related to this Jira/manager "
        "reporting routine, and suggest current tools to automate it. How "
        "many hours a year would automating it save me?"
    )
    print("\n" + plan)
