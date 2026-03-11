from __future__ import annotations

import logging

from openai import OpenAI

from .colors import COLOR_CYAN, COLOR_GREEN, COLOR_NORMAL
from .config import Config

logger = logging.getLogger(__name__)


class AIReviser:
    def __init__(self, config: Config, api_key: str):
        self.config = config
        self.client = OpenAI(api_key=api_key, base_url=config.ai_endpoint)
        self.model = config.ai_model

    def _revise(self, old_text: str, system_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": old_text},
                ],
            )
            content = response.choices[0].message.content
            if content:
                print(f"AI revise: {COLOR_CYAN}{old_text}{COLOR_NORMAL}")
                print(f"        -> {COLOR_GREEN}{content}{COLOR_NORMAL}")
                return content
            else:
                logger.warning("AI returned empty response")
                return old_text
        except Exception as e:
            logger.error("AI error: %s", e)
            return old_text

    def revise_title(self, old_title: str) -> str:
        system_prompt = """\
You are given a title name from a bibtex entry, and try to fix it.
The requirement is that the conference/journal name:
1. Transfer the title into the title upper/lower form.
2. However, there are some exceptions to rule 1.
   For some special cases where we require upper form
   (maybe some abbreviations e.g. llm -> LLM, and some proper nouns, and some project/system name),
   use "{}" around such words to indicate it is a special case, and use proper upper/lower form inside it.
   For such usage in the original title, keep the content
   inside "{}" unchanged. This is a special bibtex usage.
2. DO NOT output extra charachters; only the new title itself.

Some examples are
{RoFormer}: Enhanced Transformer with Rotary Rosition Embedding
{MemServe}: Context Caching for Disaggregated {LLM} Serving with Elastic Memory Pool
{SGLang}: Efficient Execution of Structured Language Model Programs
{CacheBlend}: Fast Large Language Model Serving for {RAG} with Cached Knowledge Fusion
{MInference} 1.0: Accelerating Pre-Filling for Long-Context {LLMs} via Dynamic Sparse Attention
{H2O:} Heavy-Hitter Oracle for Efficient Generative Inference of Large Language Models
"""
        return self._revise(old_title, system_prompt)

    def revise_journal(self, old_name: str) -> str:
        system_prompt = """\
You are given a journal name from a bibtex entry, and try to fix it.
The requirement is that
1. Change some letters from lower case to upper case, according to the convention of the journal name.
2. Only the full name, no extra abbreviation or years.
3. DO NOT output extra charachters; only the new name itself.

Some examples are
CoRR
Neurocomputing
Transactions of the Association for Computational Linguistics
"""
        return self._revise(old_name, system_prompt)

    def revise_inproceedings(self, old_name: str) -> str:
        system_prompt = """\
You are given a conference/proceeding name from a bibtex entry (the `booktitle` item), and try to fix it.
The requirement is that
1. Change some letters from lower case to upper case, according to the convention of the proceeding name.
2. Ensure a "Proceedings of" before it.
3. Only the full name, no extra abbreviation or years.
4. For "Forty-First" like words, use "Forty-First" instead of 41st.
4. DO NOT output extra charachters; only the new name itself.

Some examples are
Proceedings of the Tenth International Conference on Learning Representations
Advances in Neural Information Processing Systems Thirty-Six
Proceedings of the Twentieth European Conference on Computer Systems
Proceedings of the Twenty-Ninth Symposium on Operating Systems Principles
Proceedings of the Twenty-Third {USENIX} Conference on File and Storage Technologies
Proceedings of the Conference on Empirical Methods in Natural Language Processing
Proceedings of the Forty-First International Conference on Machine Learning
Proceedings of the Sixty-Second Annual Meeting of the Association for Computational Linguistics
Proceedings of the Sixteenth {USENIX} Symposium on Operating Systems Design and Implementation
"""
        return self._revise(old_name, system_prompt)
