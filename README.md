# Fire AI take-home: rules vs LLMs
One command: `./run_all.sh` (or `pip install -r requirements.txt && python run_all.py`). Runs 79 tests, regenerates all results to `project_a/results/` and `project_b/results/`. Offline by default.
- **LLM columns:** `export GEMINI_API_KEY=...` (and `GEMINI_MIN_INTERVAL_S=7` for the free tier) fills impl (b), the LLM extractor path, Task 5 (b) and the Project B LLM family. Without a key these print NOT MEASURED; nothing is simulated.
- **Real NYC 311:** `python -m project_b.fetch_nyc311 --max-rows 200000` (untested here: no network in the build sandbox). Without it Project B runs on clearly-labelled SYNTHETIC data.
- **Official calculator:** fill `project_a/data/official_calculator_checks.json` (48 rows), then `python -m project_a.verify_official`.
- Layout: `project_a/` (impl_a_rules, impl_b_llm, impl_c_compiled, parser, tests/oracle.py), `project_b/` (injector, detectors/{rules,statistical,llm_review}, hybrid_pipeline), results docs at the root.
## Still for you to do before submitting
1. Run with a Gemini key and paste the (b) numbers; 2. fetch real data and re-run Project B (the tables will change); 3. fill 30+ official-calculator values; 4. record your real minutes for Task 5; 5. write 20 unseen parser cases; 6. rewrite AI_USAGE.md in your own words; 7. be able to explain every file.
