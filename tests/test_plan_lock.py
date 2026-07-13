from sleep_ai_scientist.hypothesis.agents.context_agent import ContextAgent
from sleep_ai_scientist.hypothesis.agents.evolution_memory_agent import EvolutionMemoryAgent
from sleep_ai_scientist.hypothesis.agents.generation_agent import GenerationAgent
from sleep_ai_scientist.hypothesis.agents.rank_agent import RankAgent
from sleep_ai_scientist.hypothesis.agents.review_agent import ReviewAgent


def test_hypothesis_agents_are_real_classes():
    assert ContextAgent
    assert GenerationAgent
    assert ReviewAgent
    assert RankAgent
    assert EvolutionMemoryAgent
