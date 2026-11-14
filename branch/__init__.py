"""BRANCH: Belief Revising Agent for Non-expert Certified Human-in-the-loop LCA."""
__version__ = "0.1.1"

from .agent import ask_human_cli, run_agent
from .beliefs import BeliefBase, Choice
from .builder import build_model, load_spec, required_factor_keys
from .lca_model import Model, Term
from .montecarlo import State
from .query import STRATEGIES
