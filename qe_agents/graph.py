"""Builds the linear LangGraph pipeline: Planner -> Generator -> Executor -> Triager.

v2 (simplified) scope: no interrupt()/checkpointer HITL gate in this pass --
see DESIGN.md for how one would be added between plan_node and generate_node.
"""

from langgraph.graph import StateGraph, START, END

from qe_agents.executor import execute_node
from qe_agents.generator import generate_node
from qe_agents.planner import plan_node
from qe_agents.state import QEState
from qe_agents.triager import triage_node


def build_graph():
    builder = StateGraph(QEState)
    builder.add_node("planner", plan_node)
    builder.add_node("generator", generate_node)
    builder.add_node("executor", execute_node)
    builder.add_node("triager", triage_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "generator")
    builder.add_edge("generator", "executor")
    builder.add_edge("executor", "triager")
    builder.add_edge("triager", END)

    return builder.compile()
