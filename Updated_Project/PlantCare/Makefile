build-LiveWorker build-SimWorker build-LiveIngress build-SimIngress build-Heartbeat build-Api:
	python3 -m tools.package_lambda "$(ARTIFACTS_DIR)"
	python3 -m pip install -r requirements.txt --target "$(ARTIFACTS_DIR)"
