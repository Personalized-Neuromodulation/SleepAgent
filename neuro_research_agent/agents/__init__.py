from __future__ import annotations

from neuro_research_agent.agents.analyst_agent.agent import AnalystAgent
from neuro_research_agent.agents.coder_agent.agent import CoderAgent
from neuro_research_agent.agents.planner_agent.agent import PlannerAgent
from neuro_research_agent.agents.reviewer_agent.agent import ReviewerAgent
from neuro_research_agent.agents.scientist_agent.agent import ScientistAgent

analyst_agent = AnalystAgent
coder_agent = CoderAgent
planner_agent = PlannerAgent
reviewer_agent = ReviewerAgent
scientist_agent = ScientistAgent

__all__ = [
    "AnalystAgent",
    "CoderAgent",
    "PlannerAgent",
    "ReviewerAgent",
    "ScientistAgent",
    "analyst_agent",
    "coder_agent",
    "planner_agent",
    "reviewer_agent",
    "scientist_agent",
]
