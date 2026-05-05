# Project TODOs

## Evaluation & Metrics
- [ ] **fix(eval): Pre-fetch and cache document metadata for TDCE**
  - **Why**: Currently `temporal_evaluation.py` relies on a live `psycopg2` connection to calculate Authority Resolution. This makes the experiment fragile and hard to reproduce.
  - **Context**: We need to script a one-time export of metadata (authority_level, document_type, effective_date) for all documents referenced in the 100 test pairs and save it to a JSON lookup file.
  - **Depends on**: Existing Postgres DB being reachable one last time.
