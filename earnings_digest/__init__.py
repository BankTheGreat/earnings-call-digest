# provenance: aerith-direct (acknowledged-bypass: standalone extraction of Master-Bank-owned engine per approved plan swift-mixing-stallman)
"""earnings_digest — AI-agnostic YouTube -> per-stock earnings-call digest engine.

Provider-neutral core: deterministic code owns transcript acquisition,
sanitization, validation, Markdown/HTML rendering, and indexing; any LLM
(the invoking AI harness in session mode, or an API vendor via llm_client.py
in BYO-key mode) returns a structured AnalysisResult JSON object only — it
never controls the pipeline.
"""

ENGINE_VERSION = "1.0.0"
