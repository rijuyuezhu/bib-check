# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "argparse",
#     "bibtexparser==2.0.0b8",
#     "logging",
#     "openai",
#     "requests",
# ]
# ///
import argparse
import bibtexparser
import logging
import requests

from openai import OpenAI
from bibtexparser.model import Entry
from urllib.parse import urlencode

COLOR_BLACK = "\033[0;30m"
COLOR_RED = "\033[0;31m"
COLOR_GREEN = "\033[0;32m"
COLOR_YELLOW = "\033[0;33m"
COLOR_BLUE = "\033[0;34m"
COLOR_PURPLE = "\033[0;35m"
COLOR_CYAN = "\033[0;36m"
COLOR_WHITE = "\033[0;37m"
COLOR_NORMAL = "\033[0m"

logger = logging.getLogger("bib-check")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_bib_file", type=str, help="Path to the input bib file")
    parser.add_argument(
        "output_bib_file", type=str, nargs="?", help="Path to the output bib file"
    )

    # ai related
    parser.add_argument(
        "--ai", action="store_true", help="Use AI to revise some entries"
    )
    parser.add_argument(
        "--ai-service",
        type=str,
        default="deepseek",
        help="AI service name (default: deepseek)",
    )
    parser.add_argument(
        "--ai-model",
        type=str,
        default="deepseek-chat",
        help="AI model name (default: deepseek-chat)",
    )
    parser.add_argument("--ai-key", type=str, help="API key for the AI service")

    # dblp
    parser.add_argument(
        "--dblp", action="store_true", help="Convert the entry to one on DBLP"
    )

    # utils
    parser.add_argument(
        "--suppress-type",
        action="store_true",
        help="Suppress the error from unrecognized entry types",
    )
    return parser.parse_args()


class DblpSearch:
    # The following code in this class is adaptive from
    # https://github.com/alumik/dblp-api/
    #
    # MIT License
    # Copyright (c) 2021,2023 Zhong Zhenyu
    BASE_URL = "https://dblp.org/search/publ/api"

    @staticmethod
    def search(query: str) -> list[dict]:
        results = []
        options = {"q": query, "format": "json", "h": 500}
        r = requests.get(f"{DblpSearch.BASE_URL}?{urlencode(options)}").json()
        hits = r.get("result").get("hits").get("hit")
        if hits is not None:
            for hit in hits:
                info = hit.get("info")
                entry = {}
                entry["title"] = info.get("title")
                entry["year"] = info.get("year")
                entry["venue"] = info.get("venue")
                entry["doi"] = info.get("doi")
                entry["url"] = info.get("ee")
                entry["bibtex"] = f"{info.get('url')}" + ".bib"
                results.append(entry)
        return results


class BibConverter:
    def __init__(
        self,
        use_ai: bool = False,
        ai_service: str | None = None,
        ai_key: str | None = None,
        ai_model: str | None = None,
        use_dblp: bool = False,
        suppress_type: bool = False,
    ):
        self.use_ai = use_ai
        self.ai_client = None
        if use_ai:
            if not ai_service or not ai_key or not ai_model:
                raise ValueError("AI requires service, key, and model")
            self.ai_client = OpenAI(
                api_key=ai_key, base_url=f"https://api.{ai_service}.com/v1/"
            )
            self.ai_model = ai_model
        self.use_dblp = use_dblp
        self.suppress_type = suppress_type

    def check_dblp(self, entry: Entry) -> None:
        def replace_entry(hit: dict) -> None:
            bibcontent = requests.get(hit["bibtex"]).text
            lib = bibtexparser.parse_string(bibcontent)
            if len(lib.entries) != 1:
                logger.warning("Failed to parse bibtex from DBLP @ key %s", entry.key)
                return
            downloaded_entry = lib.entries[0]
            entry.fields = downloaded_entry.fields
            entry.entry_type = downloaded_entry.entry_type

        if "title" not in entry:
            logger.warning("Missing title in entry @ key %s", entry.key)
            return
        hits = DblpSearch.search(entry["title"])

        if len(hits) == 0:
            logger.warning("No hits in DBLP @ key %s", entry.key)
        elif len(hits) == 1:
            replace_entry(hits[0])
        else:
            # use a CLI to choose
            print(
                f"\nMultiple hits for {COLOR_GREEN}{entry['title']}{COLOR_NORMAL} in DBLP, please check manually"
            )
            while True:
                for i, hit in enumerate(hits):
                    print(
                        f"{i}: {COLOR_CYAN}{hit['title']}{COLOR_NORMAL}, {hit['year']}, {hit['venue']}"
                    )
                choice = input(
                    f"Please choose the correct one {COLOR_GREEN}(0-%d){COLOR_NORMAL}: "
                    % (len(hits) - 1)
                )
                if choice.isdigit() and 0 <= int(choice) < len(hits):
                    replace_entry(hits[int(choice)])
                    break
                else:
                    print("Invalid choice, input again")

    def ai_revise(self, old_name: str, system_prompt: str) -> str:
        if not self.ai_client:
            raise ValueError("AI client is not initialized")
        try:
            response = self.ai_client.chat.completions.create(
                model=self.ai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": old_name},
                ],
            )
            content = response.choices[0].message.content
            if content:
                print(f"AI revise: {COLOR_CYAN}{old_name}{COLOR_NORMAL}")
                print(f"        -> {COLOR_CYAN}{content}{COLOR_NORMAL}")
                return content
            else:
                logger.warning("AI returned empty response")
                return old_name
        except Exception as e:
            logger.error("AI error: %s", e)
            return old_name

    def ai_revise_title(self, old_title: str) -> str:
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
        return self.ai_revise(old_title, system_prompt)

    def ai_revise_journal(self, old_name: str) -> str:
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
        return self.ai_revise(old_name, system_prompt)

    def ai_revise_inproceedings(self, old_name: str) -> str:
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
Proceedings of the Advances in Neural Information Processing Systems
Proceedings of the Twentieth European Conference on Computer Systems
Proceedings of the Twenty-Ninth Symposium on Operating Systems Principles
Proceedings of the Twenty-Third {USENIX} Conference on File and Storage Technologies
Proceedings of the Conference on Empirical Methods in Natural Language Processing
Proceedings of the Forty-First International Conference on Machine Learning
Proceedings of the Sixty-Second Annual Meeting of the Association for Computational Linguistics
Proceedings of the Sixteenth {USENIX} Symposium on Operating Systems Design and Implementation
"""
        return self.ai_revise(old_name, system_prompt)

    def convert_article(self, entry: Entry) -> None:
        required = ["title", "author", "journal", "year"]
        fields = []
        for key in required:
            if key not in entry:
                logger.warning("Missing `%s` in entry @ key %s", key, entry.key)
                continue
            field = entry.fields_dict[key]
            if self.use_ai:
                if key == "title":
                    field.value = self.ai_revise_title(field.value)
                elif key == "journal":
                    field.value = self.ai_revise_journal(field.value)
            fields.append(field)
        entry.fields = fields

    def convert_inproceedings(self, entry: Entry) -> None:
        required = ["title", "author", "booktitle", "year", "pages"]
        fields = []
        for key in required:
            if key not in entry:
                logger.warning("Missing `%s` in entry @ key %s", key, entry.key)
                continue
            field = entry.fields_dict[key]
            if self.use_ai:
                if key == "title":
                    field.value = self.ai_revise_title(field.value)
                elif key == "booktitle":
                    field.value = self.ai_revise_inproceedings(field.value)
            fields.append(field)
        entry.fields = fields

    def bib_convert(self, bib_data: str, f_out: str) -> None:
        library = bibtexparser.parse_string(bib_data)
        if len(library.failed_blocks) != 0:
            f"Failed to parse {len(library.failed_blocks)} blocks"
            for block in library.failed_blocks:
                logger.warning("Failed to parse block: %s", block.error)
        for entry in library.entries:
            try:
                if self.use_dblp:
                    if (
                        entry.entry_type == "article"
                        or entry.entry_type == "inproceedings"
                    ):
                        self.check_dblp(entry)

                if entry.entry_type == "article":
                    self.convert_article(entry)
                elif entry.entry_type == "inproceedings":
                    self.convert_inproceedings(entry)
                else:
                    if not self.suppress_type:
                        logger.warning(
                            "Manually check bibentry of type %s @ key %s",
                            entry.entry_type,
                            entry.key,
                        )
            except Exception as e:
                logger.warning("Failed to convert entry @ key %s: %s", entry.key, e)
            bibtexparser.write_file(f_out, library)


def main() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        filename="bib-check.log",
        filemode="w",
        format="%(message)s",
    )
    args = parse_args()

    input_bib_file: str = args.input_bib_file
    output_bib_file: str | None = args.output_bib_file
    if output_bib_file is None:
        if input_bib_file.endswith(".bib"):
            output_bib_file = input_bib_file.replace(".bib", ".chk.bib")
        else:
            output_bib_file = input_bib_file + ".chk.bib"

    converter = BibConverter(
        use_ai=args.ai,
        ai_service=args.ai_service,
        ai_key=args.ai_key,
        ai_model=args.ai_model,
        use_dblp=args.dblp,
        suppress_type=args.suppress_type,
    )
    with open(input_bib_file, "r") as f:
        bib_data = f.read()
    converter.bib_convert(bib_data, output_bib_file)

    # print the log file
    with open("bib-check.log", "r") as f:
        log_data = f.read()
    print(
        f"\n{COLOR_RED}The main process finished. Please check the following issues (also find them in ./bib-check.log){COLOR_NORMAL}\n"
    )
    print(log_data)


if __name__ == "__main__":
    main()
