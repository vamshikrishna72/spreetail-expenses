# AI Usage

## Tools Used

- Codex/ChatGPT for planning, implementation help, debugging, and documentation.

## Key Prompts / Requests

- "Analyze this assignment and tell me what to do to get shortlisted."
- "Build the assignment honestly and make it defensible."
- "Continue; it should work well."

## How I Used AI

- To identify likely anomaly categories in the CSV.
- To draft an implementation plan.
- To write and revise the importer, app pages, and documentation.
- To generate tests that verify the importer detects the expected anomaly classes and keeps balances reconciled.

## Cases Where AI Was Wrong or Needed Correction

1. The first duplicate scan was too strict and only compared exact normalized keys. It missed fuzzy duplicates like `Dinner at Thalassa` versus `Thalassa dinner`. I corrected this by adding a description canonicalization policy and near-duplicate handling.

2. The AI initially attempted Linux-style heredoc syntax in PowerShell. PowerShell rejected it. I corrected the workflow to use PowerShell-compatible commands and then moved durable code into project files.

3. The AI tried to use an interactive choice tool that was not available in the current mode. I caught the tool error and proceeded with a direct engineering decision instead of blocking.

4. The first implementation emitted a Python `datetime.utcnow()` deprecation warning. I replaced it with timezone-aware UTC timestamps.

## Engineer-of-Record Note

AI helped produce the project, but the submitted behavior is documented in `SCOPE.md` and tested in `tests.py`. Any policy can be explained and changed because the importer logic is intentionally small and explicit.

