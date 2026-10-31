# Loads GITHUB_TOKEN and the Anthropic settings from .env (gitignored). Never commit tokens.
# Copy .env.example to .env to start.
-include .env
export GITHUB_TOKEN
# Exported only when set, so an unset one falls back to the shell or the SDK default
# instead of reaching the agents as an empty string.
$(foreach v,ANTHROPIC_API_KEY ANTHROPIC_BASE_URL ATC_MODEL,$(if $($(v)),$(eval export $(v))))

REPO := https://github.com/Jayden1905/autonomous_sg_hackathon.git
# Token goes through a credential helper, not the URL, so it never shows in `ps`.
GIT  := git -c credential.helper='!f(){ echo username=x-access-token; echo password=$$GITHUB_TOKEN; }; f'

.PHONY: help setup data semantic test demo demo-mock demo-check serve contracts push pull sync status log

help:
	@echo "Demo (local laptop):"
	@echo "  make setup      create .venv and install deps (uv)"
	@echo "  make demo-check preflight: uv, deps, API key, dataset, model, mock run, port"
	@echo "  make serve      start the API on http://localhost:8000  (then open /semantic/ and /docs)"
	@echo "  make demo       real agents on the UA599 storm scenario, in the terminal"
	@echo "  make demo-mock  same with scripted agents, no API key, under a second"
	@echo ""
	@echo "Everything else:"
	@echo "  make data       extract the organisers' Challenge 2 zip into data/"
	@echo "  make semantic   re-profile data/*.csv into semantic/schema.yaml and check the model"
	@echo "  make test       run tests (no API calls)"
	@echo "  make contracts  regenerate contracts/openapi.json and contracts/types.ts"
	@echo "  make push       push HEAD to origin/main"
	@echo "  make pull       pull --rebase from origin/main"
	@echo "  make sync       pull then push"
	@echo "  make status     git status"
	@echo "  make log        last 10 commits"

setup:
	@uv sync --extra dev

# Flattens the zip's top-level folder so files land at data/flights.csv etc.
data:
	@uv run python -c "import zipfile, glob, sys, pathlib; \
	  zs = glob.glob('Challenge 2 Airbus -*.zip') or sys.exit('put the organisers\' Challenge 2 zip in the repo root'); \
	  out = pathlib.Path('data'); out.mkdir(exist_ok=True); z = zipfile.ZipFile(zs[0]); \
	  [ (out / pathlib.Path(i.filename).name).write_bytes(z.read(i)) for i in z.infolist() if not i.is_dir() ]; \
	  print('extracted', zs[0], '->', sorted(p.name for p in out.glob('*.csv')))"

semantic:
	@uv run atc semantic profile && uv run atc semantic check

semantic-view:
	@echo "open http://localhost:8000/semantic/  (needs make serve in another terminal)"

test:
	@uv run pytest -q

DEMO_SCENARIO ?= scenarios/demo_storm_ua599.json

demo-mock:
	@uv run atc run $(DEMO_SCENARIO) --mock

demo: demo-check
	@mkdir -p traces
	@uv run atc run $(DEMO_SCENARIO) --out traces/demo.json

# Preflight for a laptop demo. Each line says what is wrong and how to fix it; exits non-zero on a blocker.
demo-check:
	@command -v uv >/dev/null || { echo "✗ uv not installed: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
	@test -x .venv/bin/python || { echo "✗ no .venv: run  make setup"; exit 1; }
	@uv run python -c "import anthropic, fastapi, duckdb, yaml" 2>/dev/null || { echo "✗ deps missing: run  make setup"; exit 1; }
	@if [ -n "$(ANTHROPIC_API_KEY)$(ANTHROPIC_AUTH_TOKEN)" ]; then echo "✓ Anthropic credentials set (model: $${ATC_MODEL:-claude-opus-5-5})"; \
	  else echo "✗ no ANTHROPIC_API_KEY: cp .env.example .env and fill it in (make demo-mock works without it)"; exit 1; fi
	@if [ -f data/flights.csv ]; then echo "✓ dataset present (SQL tool and /dot/scenarios on)"; \
	  else echo "· dataset absent: demo scenarios still work; drop the organisers' zip in the repo root and  make data  to enable the SQL tool"; fi
	@uv run atc semantic check >/dev/null && echo "✓ semantic model: all references resolve, every hard rule enforced" || { echo "✗ semantic model check failed: uv run atc semantic check"; exit 1; }
	@uv run atc run $(DEMO_SCENARIO) --mock >/dev/null && echo "✓ mock negotiation runs" || { echo "✗ mock negotiation failed"; exit 1; }
	@ss -ltn 2>/dev/null | grep -q ':8000 ' && echo "· port 8000 already in use: a server is running (fine) or stop it before  make serve" || echo "✓ port 8000 free"
	@echo "ready:  make serve   then open http://localhost:8000/semantic/  and  http://localhost:8000/docs"

serve:
	@uv run uvicorn atc_negotiation.api:app --reload --reload-include '*.yaml' --port 8000

contracts:
	@uv run python -c "import json; from atc_negotiation.api import app; \
	  open('contracts/openapi.json','w').write(json.dumps(app.openapi(), indent=2))"
	@npx -y openapi-typescript contracts/openapi.json -o contracts/types.ts
	@echo "contracts/openapi.json and contracts/types.ts regenerated"

_check-token:
	@test -n "$(GITHUB_TOKEN)" || { echo "GITHUB_TOKEN not set. Add it to .env"; exit 1; }

push: _check-token
	@$(GIT) push $(REPO) HEAD:main

pull: _check-token
	@$(GIT) pull --rebase $(REPO) main

sync: pull push

status:
	@git status

log:
	@git log --oneline -10
