#!/usr/bin/env bash
set -euo pipefail

run_test_file() {
  local start_dir="$1"
  local pattern="$2"

  python -m unittest discover -s "${start_dir}" -p "${pattern}"
}

run_test_file tests/cli/core test_portworld_cli_runtime_env_vars.py
run_test_file tests/cli/core test_portworld_cli_doctor_routing.py
run_test_file tests/cli/aws test_portworld_cli_aws_common.py
run_test_file tests/cli/aws test_portworld_cli_aws_doctor.py
run_test_file tests/cli/aws test_portworld_cli_aws_deploy.py
run_test_file tests/cli/aws test_portworld_cli_aws_runtime_env_vars.py
run_test_file tests/cli/azure test_portworld_cli_azure_doctor.py
run_test_file tests/cli/azure test_portworld_cli_azure_deploy.py
run_test_file tests/cli/azure test_portworld_cli_azure_runtime_env_vars.py
run_test_file tests/cli/core test_portworld_cli_targets.py
run_test_file tests/cli/core test_portworld_cli_project_config_v4.py
run_test_file tests/cli/core test_portworld_cli_deploy_state_targets.py
run_test_file tests/cli/core test_portworld_cli_status.py
run_test_file tests/backend test_backend_storage_settings.py
run_test_file tests/backend test_backend_object_store_factory.py
