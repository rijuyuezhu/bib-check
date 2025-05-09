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

logger = logging.getLogger("bib-check")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_bib_file", type=str, help="Path to the input bib file")
    parser.add_argument(
        "output_bib_file", type=str, nargs="?", help="Path to the output bib file"
    )
    parser.add_argument(
        "--ai", action="store_true", help="Use AI to convert some entries"
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
    parser.add_argument(
        "--dblp", action="store_true", help="Convert the entry to one on DBLP"
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

    def check_dblp(self, entry: Entry) -> None:
        def replace_entry(hit: dict) -> None:
            bibcontent = requests.get(hit["bibtex"]).text
            lib = bibtexparser.parse_string(bibcontent)
            if len(lib.entries) != 1:
                logger.warning(
                    "Failed to parse bibtex from DBLP @ line %d", entry.start_line
                )
                return
            new_entry = lib.entries[0]
            entry.fields = new_entry.fields
            entry.entry_type = new_entry.entry_type

        if "title" not in entry:
            logger.warning("Missing title in entry @ line %d", entry.start_line)
            return
        hits = DblpSearch.search(entry["title"])
        if len(hits) == 0:
            logger.warning("No hits in DBLP @ line %d", entry.start_line)
        elif len(hits) == 1:
            replace_entry(hits[0])
        else:
            # use a CLI to choose
            print(
                f"Multiple hits for \033[1;31m{entry['title']}\033[0m in DBLP, please check manually"
            )
            while True:
                for i, hit in enumerate(hits):
                    print(f"{i}: {hit['title']}, {hit['year']}, {hit['venue']}")
                choice = input(
                    "Please choose the correct one (0-%d): " % (len(hits) - 1)
                )
                if choice.isdigit() and 0 <= int(choice) < len(hits):
                    replace_entry(hits[int(choice)])
                    break
                else:
                    print("Invalid choice, input again")

    def ai_help(self, old_name: str, system_prompt: str) -> str:
        print(f"FROM: {old_name}")
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
                print(f"TO  : {content}")
                return content
            else:
                logger.warning("AI returned empty response")
                return old_name
        except Exception as e:
            logger.error("AI error: %s", e)
            return old_name

    def ai_help_title(self, old_title: str) -> str:
        system_prompt = """
You are given a title of bibtex entries, and try to fix it.
The requirement is that the conference/journal name:
1. The title is shown of the sentence form, no matter the original lower/upper form.
   So for some special cases where we require upper form (e.g. llm -> LLM, and some proper nouns),
   use "{}" around it to indicate it is a special case. For such usage in the original title, keep the content
   inside "{}" unchanged. This is a special bibtex usage. Do not change the upper/lower form of irrelavant words.
2. DO NOT output extra charachters; only the new title itself.

Some examples are
{QUEST:} Query-Aware Sparsity for Efficient Long-Context llm Inference -> {QUEST:} Query-Aware Sparsity for Efficient Long-Context {LLM} Inference
"""
        return self.ai_help(old_title, system_prompt)

    def ai_help_journal_or_booktitle(self, old_name: str) -> str:
        system_prompt = """
You are given an conference/journal name of bibtex entries, and try to fix it.
The requirement is that the conference/journal name:
1. Change some letters from lower case to upper case, according to the convention of the conference/journal name.
2. For conferences, ensure a "Proceedings of" before it.
3. Only the full name, no extra abbreviation or years.
4. For "Forty-first" like words, use "Forty-first" instead of 41st.
4. DO NOT output extra charachters; only the new name itself.

Some examples are
Proceedings of the Forty-first International Conference on Machine Learning
Proceedings of the 29th Symposium on Operating Systems Principles
"""
        return self.ai_help(old_name, system_prompt)

    def convert_article(self, entry: Entry) -> None:
        required = ["title", "author", "journal", "year"]
        fields = []
        for key in required:
            if key not in entry:
                logger.warning("Missing `%s` in entry @ line %d", key, entry.start_line)
                continue
            field = entry.fields_dict[key]
            if self.use_ai:
                if key == "title":
                    field.value = self.ai_help_title(field.value)
                elif key == "journal":
                    field.value = self.ai_help_journal_or_booktitle(field.value)
            fields.append(field)
        entry.fields = fields

    def convert_inproceedings(self, entry: Entry) -> None:
        required = ["title", "author", "booktitle", "year", "pages"]
        fields = []
        for key in required:
            if key not in entry:
                logger.warning("Missing `%s` in entry @ line %d of name %s", key, entry.start_line, entry.key)
                continue
            field = entry.fields_dict[key]
            if self.use_ai:
                if key == "title":
                    field.value = self.ai_help_title(field.value)
                elif key == "booktitle":
                    field.value = self.ai_help_journal_or_booktitle(field.value)
            fields.append(field)
        entry.fields = fields

    def bib_convert(self, bib_data: str, f_out: str) -> None:
        library = bibtexparser.parse_string(bib_data)
        assert len(library.failed_blocks) == 0, (
            f"Failed to parse {len(library.failed_blocks)} blocks"
        )
        for entry in library.entries:
            try:
                if self.use_dblp:
                    if entry.entry_type == "article" or entry.entry_type == "inproceedings":
                            self.check_dblp(entry)

                if entry.entry_type == "article":
                    self.convert_article(entry)
                elif entry.entry_type == "inproceedings":
                    self.convert_inproceedings(entry)
                else:
                    logger.warning(
                        "Manually check bibentry @ line %d of type %s",
                        entry.start_line,
                        entry.entry_type,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to convert entry @ line %d: %s", entry.start_line, e
                )
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
            output_bib_file = input_bib_file.replace(".bib", ".checked.bib")
        else:
            output_bib_file = input_bib_file + ".checked.bib"

    converter = BibConverter(
        use_ai=args.ai,
        ai_service=args.ai_service,
        ai_key=args.ai_key,
        ai_model=args.ai_model,
        use_dblp=args.dblp,
    )
    with open(input_bib_file, "r") as f:
        bib_data = f.read()
    converter.bib_convert(bib_data, output_bib_file)
    # print the log file
    with open("bib-check.log", "r") as f:
        log_data = f.read()
    print(
        "\n\033[1;31mThe main process finished. Please check the following issues\033[0;m\n"
    )
    print(log_data)


if __name__ == "__main__":
    main()
