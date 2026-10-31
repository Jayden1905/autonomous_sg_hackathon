# Loads GITHUB_TOKEN from .env (gitignored). Never commit tokens.
-include .env
export GITHUB_TOKEN

REPO := https://github.com/Jayden1905/autonomous_sg_hackathon.git
# Token goes through a credential helper, not the URL, so it never shows in `ps`.
GIT  := git -c credential.helper='!f(){ echo username=x-access-token; echo password=$$GITHUB_TOKEN; }; f'

.PHONY: help setup data test demo demo-mock serve contracts push pull sync status log

help:
	@echo "  make setup      create .venv and install deps (uv)"
	@echo "  make data       download DOT 2015 flights dataset into data/"
	@echo "  make test       run tests (no API calls)"
	@echo "  make demo-mock  scripted agents on scenarios/sample_weather.json"
	@echo "  make demo       real agents on the sample scenario"
	@echo "  make serve      API for the frontend on :8000 (docs at /docs)"
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

test:
	@uv run pytest -q

demo-mock:
	@uv run atc run scenarios/sample_weather.json --mock

demo:
	@uv run atc run scenarios/sample_weather.json --out traces/sample_weather.json

serve:
	@uv run uvicorn atc_negotiation.api:app --reload --port 8000

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
