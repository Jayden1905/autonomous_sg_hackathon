# Loads GITHUB_TOKEN from .env (gitignored). Never commit tokens.
-include .env
export GITHUB_TOKEN

REPO := https://github.com/Jayden1905/autonomous_sg_hackathon.git
# Token goes through a credential helper, not the URL, so it never shows in `ps`.
GIT  := git -c credential.helper='!f(){ echo username=x-access-token; echo password=$$GITHUB_TOKEN; }; f'

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
	@$(GIT) push $(REPO) HEAD:main

pull: _check-token
	@$(GIT) pull --rebase $(REPO) main

sync: pull push

status:
	@git status

log:
	@git log --oneline -10
