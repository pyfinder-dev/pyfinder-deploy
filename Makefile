# Every target delegates to one responsibility-specific helper.
.DEFAULT_GOAL := help
.PHONY: help setup build data finalize start stop status verify verify-live verify-caller test
COMPONENT ?=
EVIDENCE ?=
DATA_ACTION ?=
export COMPONENT DATA_ACTION EVIDENCE

help:
	@echo 'Use setup, build COMPONENT=..., data COMPONENT=shakemap DATA_ACTION=..., finalize COMPONENT=shakemap, start/stop COMPONENT=..., status, verify, verify-live COMPONENT=..., verify-caller EVIDENCE=..., or test.'

setup:
	./scripts/setup-deployment.sh
build:
	./scripts/build-deployment.sh --component "$${COMPONENT}"
data:
	./scripts/data-deployment.sh --component "$${COMPONENT}" --data-action "$${DATA_ACTION}"
finalize:
	./scripts/finalize-deployment.sh --component "$${COMPONENT}"
start:
	./scripts/start-deployment.sh --component "$${COMPONENT}"
stop:
	./scripts/stop-deployment.sh --component "$${COMPONENT}"
status:
	./scripts/status-deployment.sh
verify:
	./scripts/verify-deployment.sh
verify-live:
	./scripts/verify-deployment.sh --live --component "$${COMPONENT}"
verify-caller:
	./scripts/verify-caller-deployment.sh --evidence "$${EVIDENCE}"
test:
	./scripts/test-deployment.sh
