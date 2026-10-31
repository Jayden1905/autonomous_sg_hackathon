# Loads GITHUB_TOKEN from .env (gitignored). Never commit tokens.
-include .env

REPO := https://$(GITHUB_TOKEN)@github.com/Jayden1905/autonomous_sg_hackathon.git

.PHONY: help push pull sync status log

help:
	@echo "  make push    push HEAD to origin/main"
	@echo "  make pull    pull --rebase from origin/main"
	@echo "  make sync    pull then push"
	@echo "  make status  git status"
	@echo "  make log     last 10 commits"

_check-token:
	@test -n "$(GITHUB_TOKEN)" || { echo "GITHUB_TOKEN not set. Add it to .env"; exit 1; }

push: _check-token
	@git push $(REPO) HEAD:main

pull: _check-token
	@git pull --rebase $(REPO) main

sync: pull push

status:
	@git status

log:
	@git log --oneline -10
