# Every target delegates to one responsibility-specific helper.
.DEFAULT_GOAL := help
.PHONY: help setup build data finalize start stop status check verify verify-image verify-native verify-live verify-caller test
COMPONENT ?=
EVIDENCE ?=
DATA_ACTION ?=
export COMPONENT DATA_ACTION EVIDENCE

help:
	@echo 'Read-only: check (accumulated diagnostics), status (container state), verify (strict running wiring).'
	@echo 'Explicit checks: verify-image (offline temporary caller), verify-native (ShakeMap calculations/readiness changes), verify-caller EVIDENCE=... (temporary caller/network probe).'
	@echo 'Changes: setup, build COMPONENT=..., data COMPONENT=shakemap DATA_ACTION=..., finalize COMPONENT=shakemap, start/stop COMPONENT=...'
	@echo 'Host tests: test. Component helpers retain ownership of their workflows.'

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
check:
	./scripts/check-deployment.sh
verify:
	./scripts/verify-deployment.sh
verify-image:
	./scripts/verify-deployment.sh --live --component pyfinder
verify-native:
	./scripts/verify-deployment.sh --live --component shakemap
# Retained explicit component route; prefer the descriptive aliases above.
verify-live:
	./scripts/verify-deployment.sh --live --component "$${COMPONENT}"
verify-caller:
	./scripts/verify-caller-deployment.sh --evidence "$${EVIDENCE}"
test:
	./scripts/test-deployment.sh
