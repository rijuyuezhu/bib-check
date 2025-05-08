# bib-check

Automatically convert bibtex to a good-form one.

```
usage: bib-check.py [-h] [--ai] [--ai-service AI_SERVICE] [--ai-model AI_MODEL]
                    [--ai-key AI_KEY]
                    input_bib_file [output_bib_file]

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
```

## Usage

I recommend use `uv`:

```bash
uv run --script bib-check.py <other-args>
```
