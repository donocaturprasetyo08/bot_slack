
"""Minimal LangChain-powered helper for LLM calls.

Inspired by https://python.langchain.com/docs/tutorials/llm_chain/.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Optional

from langchain.chains import LLMChain
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI


class LLMService:
	"""LangChain wrapper around Google Gemini chat models."""

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

		model_name = model or os.getenv("LLM_MODEL", "gemini-1.5-flash")
		self._llm = ChatGoogleGenerativeAI(model=model_name, google_api_key=key, temperature=temperature)

	def run_chain(self, template: str, **inputs: Any) -> str:
		"""Render ``template`` with LangChain's :class:`LLMChain` and return text."""

		prompt = PromptTemplate(template=template, input_variables=list(inputs.keys()))
		chain = LLMChain(prompt=prompt, llm=self._llm)
		result = chain.invoke(inputs)
		return (result.get("text") or "").strip()

	def simple_completion(self, prompt: str, *, system: Optional[str] = None) -> str:
		"""Run a single-prompt request without crafting a custom template."""

		template_parts = []
		variables: Dict[str, str] = {"prompt": prompt}

		if system:
			template_parts.append("System: {system}\n")
			variables["system"] = system

		template_parts.append("User: {prompt}")
		template = "".join(template_parts)
		return self.run_chain(template, **variables)


__all__ = ["LLMService"]
