# bib-check

Automatically convert bibtex to a good-form one.

## Usage

```
usage: bib-check.py [-h] [--ai] [--ai-service AI_SERVICE] [--ai-model AI_MODEL] [--ai-key AI_KEY] [--dblp] input_bib_file [output_bib_file]

positional arguments:
  input_bib_file        Path to the input bib file
  output_bib_file       Path to the output bib file

options:
  -h, --help            show this help message and exit
  --ai                  Use AI to convert some entries
  --ai-service AI_SERVICE
                        AI service name (default: deepseek)
  --ai-model AI_MODEL   AI model name (default: deepseek-chat)
  --ai-key AI_KEY       API key for the AI service
  --dblp                Convert the entry to one on DBLP
```

I recommend use `uv` to run the script, which reads the dependencies from the script itself

```bash
uv run bib-check.py <other-args>
```

## Workflow

I recommend using two phases to run the script.

First check the dblp, and fix the issues if any.

```bash
uv run bib-check.py 1.bib 2.bib --dblp
```

Then use ai to convert the titles/entries

```bash
uv run bib-check.py 2.bib 3.bib --ai --ai-service <service> --ai-model <model> --ai-key <key>
```

After that, diff `2.bib` and `3.bib` to ensure correctness.
