
"""Minimal LangGraph-powered helper for LLM calls.

Uses LangGraph for orchestrating LLM interactions with Google Gemini.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional, TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END


class LLMState(TypedDict):
	"""State for the LLM graph."""
	messages: list
	result: Optional[str]


class LLMService:
	"""LangGraph wrapper around Google Gemini chat models."""

	def __init__(
		self,
		*,
		model: Optional[str] = None,
		api_key: Optional[str] = None,
		temperature: float = 0.2,
	):
		key = api_key or os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
		if not key:
			raise ValueError("Set LLM_API_KEY or GEMINI_API_KEY to use LLMService")

		model_name = model or os.getenv("LLM_MODEL", "gemini-2.5-flash")
		self._llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=key, temperature=temperature)

		# Build the LangGraph
		self._graph = self._build_graph()

	def _build_graph(self) -> Any:
		"""Build the LangGraph for LLM interactions."""
		def call_llm(state: LLMState) -> LLMState:
			"""Node function that calls the LLM."""
			messages = state["messages"]
			response = self._llm.invoke(messages)
			return {"messages": messages, "result": response.content.strip()}

		graph = StateGraph(LLMState)
		graph.add_node("llm", call_llm)
		graph.add_edge(START, "llm")
		graph.add_edge("llm", END)
		return graph.compile()

	def run_chain(self, template: str, **inputs: Any) -> str:
		"""Render template and run through LangGraph."""
		from langchain_core.prompts import PromptTemplate
		from langchain_core.messages import HumanMessage

		prompt = PromptTemplate(template=template, input_variables=list(inputs.keys()))
		formatted_prompt = prompt.format(**inputs)

		initial_state: LLMState = {
			"messages": [HumanMessage(content=formatted_prompt)],
			"result": None
		}

		final_state = self._graph.invoke(initial_state)
		return final_state["result"] or ""

	def simple_completion(self, prompt: str, *, system: Optional[str] = None) -> str:
		"""Run a single-prompt request through LangGraph."""
		from langchain_core.messages import HumanMessage, SystemMessage

		messages = []
		if system:
			messages.append(SystemMessage(content=system))
		messages.append(HumanMessage(content=prompt))

		initial_state: LLMState = {
			"messages": messages,
			"result": None
		}

		final_state = self._graph.invoke(initial_state)
		return final_state["result"] or ""


__all__ = ["LLMService"]
