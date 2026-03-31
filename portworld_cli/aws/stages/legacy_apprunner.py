from __future__ import annotations

from collections import OrderedDict
from time import monotonic
import time

from portworld_cli.aws.common import run_aws_json
from portworld_cli.aws.constants import (
    APP_RUNNER_ECR_ROLE_NAME,
    APP_RUNNER_INSTANCE_CPU,
    APP_RUNNER_INSTANCE_MEMORY,
    APP_RUNNER_INSTANCE_POLICY_NAME,
    APP_RUNNER_INSTANCE_ROLE_SUFFIX,
)
from portworld_cli.aws.stages.config import ResolvedAWSDeployConfig
from portworld_cli.aws.stages.shared import normalize_service_url, read_dict_string, stage_ok, to_json_argument
from portworld_cli.deploy.config import DeployStageError


def ensure_apprunner_ecr_access_role(*, stage_records: list[dict[str, object]]) -> str:
    role = run_aws_json(["iam", "get-role", "--role-name", APP_RUNNER_ECR_ROLE_NAME])
    if role.ok and isinstance(role.value, dict):
        role_payload = role.value.get("Role")
        if isinstance(role_payload, dict):
            role_arn = read_dict_string(role_payload, "Arn")
            if role_arn:
                stage_records.append(stage_ok("iam_apprunner_ecr_role", f"IAM role `{APP_RUNNER_ECR_ROLE_NAME}` is ready."))
                return role_arn

    lowered = (role.message or "").lower()
    if "nosuchentity" not in lowered and "not found" not in lowered:
        raise DeployStageError(
            stage="iam_apprunner_ecr_role",
            message=role.message or "Unable to inspect IAM role for App Runner ECR access.",
            action="Verify IAM permissions for iam:GetRole.",
        )

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "build.apprunner.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    created = run_aws_json(
        [
            "iam",
            "create-role",
            "--role-name",
            APP_RUNNER_ECR_ROLE_NAME,
            "--assume-role-policy-document",
            to_json_argument(trust_policy),
        ]
    )
    if not created.ok or not isinstance(created.value, dict):
        raise DeployStageError(
            stage="iam_apprunner_ecr_role",
            message=created.message or "Unable to create IAM role for App Runner ECR access.",
            action="Grant iam:CreateRole and retry.",
        )
    attach = run_aws_json(
        [
            "iam",
            "attach-role-policy",
            "--role-name",
            APP_RUNNER_ECR_ROLE_NAME,
            "--policy-arn",
            "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess",
        ]
    )
    if not attach.ok:
        raise DeployStageError(
            stage="iam_apprunner_ecr_role",
            message=attach.message or "Unable to attach App Runner ECR access policy.",
            action="Grant iam:AttachRolePolicy and retry.",
        )
    stage_records.append(stage_ok("iam_apprunner_ecr_role", f"Created IAM role `{APP_RUNNER_ECR_ROLE_NAME}`."))
    created_role = created.value.get("Role")
    if not isinstance(created_role, dict):
        raise DeployStageError(
            stage="iam_apprunner_ecr_role",
            message="IAM create-role response did not include role details.",
            action="Retry deploy.",
        )
    role_arn = read_dict_string(created_role, "Arn")
    if not role_arn:
        raise DeployStageError(
            stage="iam_apprunner_ecr_role",
            message="Unable to resolve IAM role ARN for App Runner ECR role.",
            action="Retry deploy.",
        )
    return role_arn


def ensure_apprunner_instance_role(
    *,
    config: ResolvedAWSDeployConfig,
    stage_records: list[dict[str, object]],
) -> str:
    role_name = f"{config.app_name}-{APP_RUNNER_INSTANCE_ROLE_SUFFIX}"
    role = run_aws_json(["iam", "get-role", "--role-name", role_name])
    if role.ok and isinstance(role.value, dict):
        role_payload = role.value.get("Role")
        if isinstance(role_payload, dict):
            role_arn = read_dict_string(role_payload, "Arn")
            if role_arn:
                put_apprunner_instance_role_policy(
                    role_name=role_name,
                    bucket_name=config.bucket_name,
                )
                stage_records.append(
                    stage_ok("iam_apprunner_instance_role", f"IAM role `{role_name}` is ready.")
                )
                return role_arn

    lowered = (role.message or "").lower()
    if "nosuchentity" not in lowered and "not found" not in lowered:
        raise DeployStageError(
            stage="iam_apprunner_instance_role",
            message=role.message or "Unable to inspect IAM role for App Runner runtime access.",
            action="Verify IAM permissions for iam:GetRole.",
        )

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }
    created = run_aws_json(
        [
            "iam",
            "create-role",
            "--role-name",
            role_name,
            "--assume-role-policy-document",
            to_json_argument(trust_policy),
        ]
    )
    if not created.ok or not isinstance(created.value, dict):
        raise DeployStageError(
            stage="iam_apprunner_instance_role",
            message=created.message or "Unable to create IAM role for App Runner runtime access.",
            action="Grant iam:CreateRole and retry.",
        )
    put_apprunner_instance_role_policy(role_name=role_name, bucket_name=config.bucket_name)
    stage_records.append(stage_ok("iam_apprunner_instance_role", f"Created IAM role `{role_name}`."))
    created_role = created.value.get("Role")
    if not isinstance(created_role, dict):
        raise DeployStageError(
            stage="iam_apprunner_instance_role",
            message="IAM create-role response did not include role details.",
            action="Retry deploy.",
        )
    role_arn = read_dict_string(created_role, "Arn")
    if not role_arn:
        raise DeployStageError(
            stage="iam_apprunner_instance_role",
            message="Unable to resolve IAM role ARN for App Runner runtime role.",
            action="Retry deploy.",
        )
    return role_arn


def put_apprunner_instance_role_policy(*, role_name: str, bucket_name: str) -> None:
    policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:ListBucket"],
                "Resource": [f"arn:aws:s3:::{bucket_name}"],
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:DeleteObject",
                ],
                "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
            },
        ],
    }
    put_policy = run_aws_json(
        [
            "iam",
            "put-role-policy",
            "--role-name",
            role_name,
            "--policy-name",
            APP_RUNNER_INSTANCE_POLICY_NAME,
            "--policy-document",
            to_json_argument(policy_document),
        ]
    )
    if not put_policy.ok:
        raise DeployStageError(
            stage="iam_apprunner_instance_role",
            message=put_policy.message or "Unable to apply inline App Runner runtime policy.",
            action="Grant iam:PutRolePolicy and retry.",
        )


def upsert_apprunner_service(
    config: ResolvedAWSDeployConfig,
    *,
    access_role_arn: str,
    instance_role_arn: str,
    runtime_env: OrderedDict[str, str],
    stage_records: list[dict[str, object]],
) -> tuple[str, str]:
    service_arn = find_apprunner_service_arn(region=config.region, service_name=config.app_name)
    source_configuration = build_apprunner_source_configuration(
        image_uri=config.image_uri,
        access_role_arn=access_role_arn,
        runtime_env=runtime_env,
    )
    health_check = {
        "Protocol": "TCP",
        "Interval": 10,
        "Timeout": 5,
        "HealthyThreshold": 1,
        "UnhealthyThreshold": 5,
    }
    instance_configuration = {
        "Cpu": APP_RUNNER_INSTANCE_CPU,
        "Memory": APP_RUNNER_INSTANCE_MEMORY,
        "InstanceRoleArn": instance_role_arn,
    }
    if service_arn is None:
        created = run_aws_json(
            [
                "apprunner",
                "create-service",
                "--region",
                config.region,
                "--service-name",
                config.app_name,
                "--source-configuration",
                to_json_argument(source_configuration),
                "--instance-configuration",
                to_json_argument(instance_configuration),
                "--health-check-configuration",
                to_json_argument(health_check),
            ]
        )
        if not created.ok or not isinstance(created.value, dict):
            raise DeployStageError(
                stage="apprunner_service",
                message=created.message or "Unable to create App Runner service.",
                action="Verify apprunner:CreateService permissions.",
            )
        service = created.value.get("Service")
        if not isinstance(service, dict):
            raise DeployStageError(
                stage="apprunner_service",
                message="App Runner create-service response missing Service payload.",
                action="Retry deploy.",
            )
        service_arn = read_dict_string(service, "ServiceArn")
        if not service_arn:
            raise DeployStageError(
                stage="apprunner_service",
                message="Unable to resolve App Runner service ARN.",
                action="Retry deploy.",
            )
        stage_records.append(stage_ok("apprunner_service", f"Created App Runner service `{config.app_name}`."))
    else:
        updated = run_aws_json(
            [
                "apprunner",
                "update-service",
                "--region",
                config.region,
                "--service-arn",
                service_arn,
                "--source-configuration",
                to_json_argument(source_configuration),
                "--instance-configuration",
                to_json_argument(instance_configuration),
                "--health-check-configuration",
                to_json_argument(health_check),
            ]
        )
        if not updated.ok:
            raise DeployStageError(
                stage="apprunner_service",
                message=updated.message or "Unable to update App Runner service.",
                action="Verify apprunner:UpdateService permissions.",
            )
        stage_records.append(stage_ok("apprunner_service", f"Updated App Runner service `{config.app_name}`."))

    service_url = wait_for_apprunner_running(
        region=config.region,
        service_arn=service_arn,
        stage_records=stage_records,
    )
    return service_arn, service_url


def build_apprunner_source_configuration(
    *,
    image_uri: str,
    access_role_arn: str,
    runtime_env: OrderedDict[str, str],
) -> dict[str, object]:
    return {
        "AuthenticationConfiguration": {
            "AccessRoleArn": access_role_arn,
        },
        "AutoDeploymentsEnabled": False,
        "ImageRepository": {
            "ImageIdentifier": image_uri,
            "ImageRepositoryType": "ECR",
            "ImageConfiguration": {
                "Port": "8080",
                "RuntimeEnvironmentVariables": dict(runtime_env),
            },
        },
    }


def find_apprunner_service_arn(*, region: str, service_name: str) -> str | None:
    listed = run_aws_json(["apprunner", "list-services", "--region", region])
    if not listed.ok or not isinstance(listed.value, dict):
        return None
    summaries = listed.value.get("ServiceSummaryList")
    if not isinstance(summaries, list):
        return None
    for summary in summaries:
        if not isinstance(summary, dict):
            continue
        if read_dict_string(summary, "ServiceName") == service_name:
            return read_dict_string(summary, "ServiceArn")
    return None


def wait_for_apprunner_running(
    *,
    region: str,
    service_arn: str,
    stage_records: list[dict[str, object]],
) -> str:
    deadline = monotonic() + 20 * 60
    while monotonic() < deadline:
        described = run_aws_json(
            ["apprunner", "describe-service", "--region", region, "--service-arn", service_arn]
        )
        if not described.ok or not isinstance(described.value, dict):
            raise DeployStageError(
                stage="apprunner_service_wait_running",
                message=described.message or "Unable to describe App Runner service.",
                action="Verify apprunner:DescribeService permissions.",
            )
        service = described.value.get("Service")
        if not isinstance(service, dict):
            raise DeployStageError(
                stage="apprunner_service_wait_running",
                message="App Runner describe-service response missing Service payload.",
                action="Retry deploy.",
            )
        status = read_dict_string(service, "Status") or "UNKNOWN"
        if status == "RUNNING":
            raw_service_url = read_dict_string(service, "ServiceUrl")
            if not raw_service_url:
                raise DeployStageError(
                    stage="apprunner_service_wait_running",
                    message="App Runner service reached RUNNING but service URL is missing.",
                    action="Inspect App Runner service details in AWS console.",
                )
            service_url = normalize_service_url(raw_service_url)
            stage_records.append(stage_ok("apprunner_service_wait_running", f"App Runner service is RUNNING: {service_url}"))
            return service_url
        if status.endswith("FAILED") or status in {"DELETED"}:
            raise DeployStageError(
                stage="apprunner_service_wait_running",
                message=f"App Runner service entered terminal status `{status}`.",
                action="Inspect App Runner operation events/logs and retry.",
            )
        time.sleep(8)

    raise DeployStageError(
        stage="apprunner_service_wait_running",
        message="Timed out waiting for App Runner service to become RUNNING.",
        action="Inspect App Runner service status and logs.",
    )
