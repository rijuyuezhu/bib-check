# bib-check

Automatically convert bibtex to a good-form one.

## Usage

```
usage: bib-check [-h] [--ai] [--ai-endpoint AI_ENDPOINT] [--ai-model AI_MODEL]
                 [--ai-key-env AI_KEY_ENV] [--dblp] [--suppress-type] [--tui]
                 input_bib_file [output_bib_file]

positional arguments:
  input_bib_file        Path to the input bib file
  output_bib_file       Path to the output bib file

options:
  -h, --help            show this help message and exit
  --ai                  Use AI to revise some entries
  --ai-endpoint AI_ENDPOINT
                        AI API endpoint (default: https://api.deepseek.com/v1)
  --ai-model AI_MODEL   AI model name (default: deepseek-chat)
  --ai-key-env AI_KEY_ENV
                        Environment variable name containing the API key (default: DEEPSEEK_API_KEY)
  --dblp                Convert the entry to one on DBLP
  --suppress-type       Suppress the error from unrecognized entry types
  --tui                 Use interactive TUI mode
```

[`uv`](https://docs.astral.sh/uv/) is recommended to run the tool:

```bash
uv run bib-check <other-args>
```

## TUI Mode

Launch the interactive TUI with `--tui`:

```bash
uv run bib-check input.bib --tui
```

The TUI provides a vim-like interface for reviewing and transforming entries:

- **Navigation:** `j`/`k` or arrow keys to move, `gg`/`G` to jump to top/bottom
- **Selection:** `Space` to toggle, `v` for visual mode, `a`/`A` to select/deselect all
- **Actions on selected entries:**
  - `d` — DBLP search and replace
  - `r` — AI revise (requires `--ai`)
  - `f` — Format (strip to required fields)
  - `w` — Write output file
- **Other:** `v` to toggle verbose view, `h` for help, `q` to quit

On exit, the output is always written automatically.

## Workflow

My workflow is listed below for your reference.

1. **Start.** Prepare a start file named `1.bib`:
   ```bash
   $ cp <origin-bib-file> 1.bib
   ```
2. **Search on DBLP.** Replace each of the entries with the one on DBLP:
   ```bash
   $ uv run bib-check 1.bib 2.bib --dblp
   ```
   In this process, some interactive selections may be required for multiple entries found; select them carefully for the best one.
3. **Handle issues reported in step 2.** First do a backup:
   ```bash
   $ cp 2.bib 3.bib
   ```
   Then in `3.bib`, for each issues reported by the command in step 2:
   - `Manually check bibentry of type misc @ key ...`: the entry is not of type `@journal` or `@inproceedings`; you are expected to check it manually;
   - `No hits in DBLP @ key %s`: the entry is not found in DBLP; you are expected to check it manually;
   - `Missing "pages" in entry @ key ...`: one field (typically `pages`) is missing for the entry; find it manually;
   - Also, for every `CoRR` entry (arXiv), search the title/authors in DBLP to manually to ensure the entry is correct. This is because many papers have different names on arXiv and the proceedings.
     After that, reformat the bib file; now add `--suppress-type` to suppress the error from unrecognized entry types:
   ```bash
   uv run bib-check 3.bib 4.bib --suppress-type
   ```
4. **Use ai to revise the `title/journal/booktitle` fields.**
   ```bash
   uv run bib-check 4.bib 5.bib --suppress-type --ai
   ```
   After that, using diff tools to check the differences between `4.bib` and `5.bib`, and do some appropriate modifications.
   ```bash
   $ code --diff 4.bib 5.bib
   # or using nvim
   $ nvim -d 4.bib 5.bib
   ```
5. **Finish.** Finally, reformat the bib file:
   ```bash
   $ uv run bib-check 5.bib final.bib --suppress-type
   ```
   Now you can use `final.bib` in your LaTeX project.
