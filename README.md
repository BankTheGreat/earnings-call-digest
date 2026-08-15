# Earnings-Call Digest

Turn a YouTube earnings-call or Opportunity-Day (OppDay) video into a polished,
**quote-verified**, per-stock HTML digest — an impact-ordered executive summary,
key claims with timestamped quotes, a grouped numbers table, a bull-vs-bear
board, a value-investing lens, and a management-tone read.

It is **AI-agnostic**. You can run it two ways:

- **Session mode ($0):** if you are already inside an AI coding assistant (Claude
  Code, or any harness that can read a file and write JSON), the tool fetches and
  sanitizes the transcript, and *your assistant* writes the analysis. No API key,
  no per-token spend.
- **BYO-key mode:** point it at your own Gemini / OpenAI / Anthropic API key and it
  runs the analysis headless, end to end.

The pipeline is deterministic where it matters: Python owns transcript
acquisition, sanitization, validation, and rendering. The LLM only ever returns
a structured `AnalysisResult` JSON object — it never controls the pipeline, and
every claim it makes is checked back against the transcript before it reaches the
page.

---

## Why quote-verified?

An LLM asked to summarize a two-hour call will occasionally invent a number or a
quote. This tool defends against that mechanically:

- Every key claim and every quote must **anchor to a real span of the
  transcript**. Anchors are checked after generation.
- If too large a share of the claimed quotes cannot be found in the transcript,
  the whole analysis is **rejected** (the transcript is kept; nothing is filed).
- Optionally, spoken numbers are **cross-checked against the company's own PDFs**
  (slide deck / MD&A) by digit-presence — see *Document grounding* below.

The goal is simple: a page you can trust enough to act on, or an honest refusal.

---

## Install

```bash
pip install earnings-call-digest
```

Or from source:

```bash
git clone https://github.com/BankTheGreat/earnings-call-digest
cd earnings-call-digest
pip install -e .
```

Requires Python 3.9+. Dependencies: `yt-dlp`, `httpx`, `youtube-transcript-api`,
`pypdf`. If YouTube changes its site and fetches start failing, update the
fetcher: `pip install -U yt-dlp`.

---

> 📖 **New here? The full step-by-step guide is in [USAGE.md](USAGE.md).**

## Quick start

### 1. Session mode (no API key)

```bash
earnings-digest run "https://www.youtube.com/watch?v=VIDEO_ID" --ticker TU.BK --engine session
```

This fetches + sanitizes the transcript, then prints a short hand-off telling the
invoking assistant which file to read, which persona template to follow, and how
to finalize. Your assistant writes the `AnalysisResult` JSON to a temp file, then:

```bash
earnings-digest finalize VIDEO_ID --analysis-json out.json --summary-mode session --summary-model <model-id>
```

The finished HTML lands in `./out/`.

### 2. BYO-key mode (headless)

```bash
export GEMINI_API_KEY=...        # or OPENAI_API_KEY / ANTHROPIC_API_KEY
earnings-digest run "https://youtu.be/VIDEO_ID" --ticker TU.BK --engine api
```

The key is read from the vendor's own environment variable — it is never a CLI
argument and never written to disk. Pick the vendor/model with `--vendor` /
`--model`; cap spend with `--max-spend` (a cost estimate prints before the call).

### 3. Discover by ticker + quarter (best-effort)

If you do not have the URL, the tool can search YouTube for you:

```bash
earnings-digest run --ticker TU.BK --quarter Q2/2026 --engine session
```

Discovery is **never-guess**: a candidate is accepted only if its title contains
both the ticker and the quarter (Gregorian *or* Thai Buddhist-Era year). If it
finds zero or several plausible matches, it prints the candidate list and asks
you to re-run with the exact URL — it will not auto-file the wrong company.

---

## Document grounding (optional)

Give the tool the company's own PDFs and it will confirm the spoken numbers
against them by digit-presence (no rescaling, no guessing):

```bash
earnings-digest run "<url>" --ticker TU.BK --slide oppday_q2.pdf --mda mda_q2.pdf
```

Each number in the digest is then marked as confirmed by the slide deck, the
MD&A, both, or neither. With no PDFs supplied, the digest still renders — the
grounding badges simply read "no documents supplied" (honest, never a false
confirmation).

---

## Output

For each video you get, under `./out/<MARKET>/<TICKER>/`:

- a self-contained **HTML** digest (dark-mode default with a light toggle,
  no external assets), and
- a **Markdown** source of the same content, plus
- an append-only `index.jsonl` you can build a dashboard from.

The machine cache (raw transcript + analysis JSON per video) lives under
`./.cache/` and is safe to delete; renders can be regenerated from it with
`earnings-digest rerender`.

Change the output directory with `--out <dir>`.

---

## Security & privacy

This tool fetches third-party video transcripts and can call an LLM with your
key. It was built against a four-category security review; the posture is:

**1. Credentials / key handling.** API keys are read only from the vendor's own
environment variable. They are never accepted as CLI arguments, never written to
any file, and never logged. Vendor error messages are surfaced with the reason
kept but any key-shaped token scrubbed, so a failure never leaks a key into your
terminal or logs.

**2. Untrusted input / injection.** A YouTube transcript is **untrusted data,
not instructions.** Before any LLM sees it, the transcript is passed through a
sanitizer that neutralizes common prompt-injection patterns, and it is fenced as
data in the prompt. In session mode the hand-off explicitly tells the assistant
to treat the transcript as data. The LLM's reply is parsed as JSON only — it can
never trigger a tool call or a shell command through this tool.

**3. Abuse / cost / availability.** BYO-key mode prints a cost estimate and
enforces a `--max-spend` cap *before* the call. Network fetches retry a bounded
number of times and then fail with a typed error rather than hanging. There is a
kill switch: set `ECD_DISABLED=1` to disable all runs. Use the tool at human
scale — it is not a bulk scraper, and heavy automated use will get your IP
rate-limited by YouTube.

**4. Authorization / scope.** The tool only ever reads the URL you give it (or a
candidate you confirm) and only ever writes under your chosen output and cache
directories. It does not read your files, your history, or any private corpus; it
scans no directory you did not point it at. Document grounding reads only the PDF
paths you pass explicitly.

No private data is bundled with this package.

---

## Troubleshooting

- **"no captions available"** — the video has neither manual nor auto captions in
  the requested languages. Supply your own with `--transcript-file <file.vtt|srt|txt>`.
- **High "unverified quote" count / rejection** — usually a low-quality
  auto-caption track (common for non-English audio). That is the safety feature
  working. Try a manual-caption video or supply a cleaner transcript file.
- **"live video"** — the stream has not finished processing; retry after it ends.
- **discovery finds nothing** — pass the exact `--url`; title conventions vary.

---

## License

MIT — see [LICENSE](LICENSE).
