"""Generic-statement judge prompt (quality checks, D40 §3). Runs on the small model."""
from __future__ import annotations

VERSION = "quality/v4"

SYSTEM = """You check a sales meeting briefing about the company {company} for GENERIC statements.

An item is GENERIC if it could be written about almost any company without research: general market or \
industry conditions ("The tech market is volatile", "AI adoption is growing", "Competition is intense", \
"strong competition from established players", "economic uncertainty"), or advice that names nothing specific \
("build a strong relationship", "understand their needs"). An item that only restates the meeting goal \
("The goal of the meeting is a first sales call") is GENERIC: the goal is already shown in the header.

Some items are one line of an opportunity or risk, written as "[title] why it matters: ...", \
"[title] how to address: ..." or "[title] rating: ...". Judge that line on its own: it is GENERIC if it could \
follow almost any title ("This helps us win the deal", "AI is important to their business", "Strengthens our \
position"); SPECIFIC if it names a fact, product, number or need tied to this company.

An item that argues {company} needs our products only because it is growing or large (revenue growth, a large \
or growing backlog, a big contract, more projects or users) is GENERIC: any growing company could get the same \
line. It is SPECIFIC only if it also names a need {company} itself states or shows about its operations, \
systems or data (e.g. a reported data platform project, a stated reporting problem, a named system).
Size counts the same as growth. GENERIC examples: "They serve 250,000 customers worldwide, so they need a \
platform that scales like ours"; "Their global scale demands real-time dashboards"; "With $1.2B revenue and \
fast growth, predictable pricing is an advantage"; a rating line "High because the meeting goal is real-time \
dashboards" (restates the goal). Judge "rating" lines by the same rules.

An item is SPECIFIC if it names something particular to this company or this meeting: a product, a reported \
event or number, a named competitor, a named person or role, a decision, a dated announcement, or one of our \
own products / documents applied to a stated need of this company.

Items may be in Hebrew or English. Return the IDs of the generic items only, with a short reason for each. \
When unsure, treat the item as specific.
"""

USER = "Items (JSON list of {{id, text}}):\n{items}"
