from __future__ import annotations

from dataclasses import dataclass
import os

from portworld_cli.aws.common import (
    aws_cli_available,
    is_postgres_url,
    normalize_optional_text,
    run_aws_json,
    run_aws_text,
    split_csv_values,
    validate_s3_bucket_name,
)
from portworld_cli.output import DiagnosticCheck
from portworld_cli.workspace.project_config import ProjectConfig


@dataclass(frozen=True, slots=True)
class AWSDoctorDetails:
    account_id: str | None
    arn: str | None
    region: str | None
    cluster_name: str | None
    service_name: str | None
    vpc_id: str | None
    subnet_ids: tuple[str, ...]
    certificate_arn: str | None
    bucket_name: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "arn": self.arn,
            "region": self.region,
            "cluster_name": self.cluster_name,
            "service_name": self.service_name,
            "vpc_id": self.vpc_id,
            "subnet_ids": list(self.subnet_ids),
            "certificate_arn": self.certificate_arn,
            "bucket_name": self.bucket_name,
        }


@dataclass(frozen=True, slots=True)
class AWSDoctorEvaluation:
    ok: bool
    checks: tuple[DiagnosticCheck, ...]
    details: AWSDoctorDetails


def evaluate_aws_ecs_fargate_readiness(
    *,
    explicit_region: str | None,
    explicit_cluster: str | None,
    explicit_service: str | None,
    explicit_vpc_id: str | None,
    explicit_subnet_ids: str | None,
    explicit_certificate_arn: str | None,
    explicit_database_url: str | None,
    explicit_s3_bucket: str | None,
    env_values: dict[str, str],
    project_config: ProjectConfig | None,
) -> AWSDoctorEvaluation:
    checks: list[DiagnosticCheck] = []

    aws_defaults = None if project_config is None else project_config.deploy.aws_ecs_fargate

    region = _first_non_empty(
        explicit_region,
        None if aws_defaults is None else aws_defaults.region,
        os.environ.get("AWS_REGION"),
        os.environ.get("AWS_DEFAULT_REGION"),
    )

    cluster_name = _first_non_empty(
        explicit_cluster,
        None if aws_defaults is None else aws_defaults.cluster_name,
    )
    service_name = _first_non_empty(
        explicit_service,
        None if aws_defaults is None else aws_defaults.service_name,
    )
    vpc_id = _first_non_empty(
        explicit_vpc_id,
        None if aws_defaults is None else aws_defaults.vpc_id,
    )
    subnet_ids = _resolve_subnets(
        explicit_value=explicit_subnet_ids,
        configured=(() if aws_defaults is None else aws_defaults.subnet_ids),
    )
    certificate_arn = normalize_optional_text(explicit_certificate_arn)

    database_url = _first_non_empty(
        explicit_database_url,
        env_values.get("BACKEND_DATABASE_URL"),
    )
    bucket_name = _first_non_empty(
        explicit_s3_bucket,
        env_values.get("BACKEND_OBJECT_STORE_NAME"),
        env_values.get("BACKEND_OBJECT_STORE_BUCKET"),
    )

    cli_ok = aws_cli_available()
    checks.append(
        DiagnosticCheck(
            id="aws_cli_installed",
            status="pass" if cli_ok else "fail",
            message="aws CLI is installed" if cli_ok else "aws CLI is not installed or not on PATH.",
            action=None if cli_ok else "Install AWS CLI v2 and re-run doctor.",
        )
    )

    account_id: str | None = None
    arn: str | None = None
    if cli_ok:
        identity = run_aws_json(["sts", "get-caller-identity"])  # region not required
        if identity.ok and isinstance(identity.value, dict):
            account_id = _read_dict_string(identity.value, "Account")
            arn = _read_dict_string(identity.value, "Arn")
            checks.append(
                DiagnosticCheck(
                    id="aws_authenticated",
                    status="pass",
                    message=f"Authenticated AWS identity: {arn or 'unknown'}",
                )
            )
        else:
            checks.append(
                DiagnosticCheck(
                    id="aws_authenticated",
                    status="fail",
                    message=identity.message or "Unable to resolve AWS caller identity.",
                    action="Run `aws configure` or set AWS credentials and retry.",
                )
            )

    if region is None and cli_ok:
        configured_region = run_aws_text(["configure", "get", "region"])
        if configured_region.ok and isinstance(configured_region.value, str):
            region = normalize_optional_text(configured_region.value)

    checks.append(
        DiagnosticCheck(
            id="aws_region_selected",
            status="pass" if region else "fail",
            message=(
                f"Using AWS region '{region}'."
                if region
                else "No AWS region resolved for ECS/Fargate checks."
            ),
            action=None if region else "Pass --aws-region or set AWS_REGION/AWS_DEFAULT_REGION.",
        )
    )

    checks.extend(
        [
            _required_value_check("aws_cluster_selected", cluster_name, "--aws-cluster is required."),
            _required_value_check("aws_service_selected", service_name, "--aws-service is required."),
            _required_value_check("aws_vpc_selected", vpc_id, "--aws-vpc-id is required."),
            DiagnosticCheck(
                id="aws_subnets_selected",
                status="pass" if subnet_ids else "fail",
                message=(
                    f"Using subnet ids: {', '.join(subnet_ids)}"
                    if subnet_ids
                    else "No AWS subnets resolved."
                ),
                action=None if subnet_ids else "Pass --aws-subnet-ids (comma-separated).",
            ),
            _required_value_check(
                "aws_certificate_selected",
                certificate_arn,
                "--aws-certificate-arn is required for ALB HTTPS listener validation.",
            ),
        ]
    )

    db_ok = bool(database_url and is_postgres_url(database_url))
    checks.append(
        DiagnosticCheck(
            id="database_url_ready",
            status="pass" if db_ok else "fail",
            message=(
                "BACKEND_DATABASE_URL is present and uses a PostgreSQL scheme."
                if db_ok
                else "BACKEND_DATABASE_URL is missing or not PostgreSQL-shaped."
            ),
            action=None if db_ok else "Set BACKEND_DATABASE_URL to an existing PostgreSQL connection URL.",
        )
    )

    if bucket_name is None:
        checks.append(
            DiagnosticCheck(
                id="s3_bucket_name_valid",
                status="fail",
                message="No managed object-store bucket name resolved.",
                action="Set BACKEND_OBJECT_STORE_NAME or pass --aws-s3-bucket.",
            )
        )
    else:
        bucket_validation_error = validate_s3_bucket_name(bucket_name)
        checks.append(
            DiagnosticCheck(
                id="s3_bucket_name_valid",
                status="pass" if bucket_validation_error is None else "fail",
                message=(
                    f"S3 bucket name '{bucket_name}' is valid."
                    if bucket_validation_error is None
                    else bucket_validation_error
                ),
                action=None if bucket_validation_error is None else "Choose a valid S3 bucket name.",
            )
        )

    if cli_ok and region and subnet_ids:
        subnet_result = run_aws_json(["ec2", "describe-subnets", "--subnet-ids", *subnet_ids, "--region", region])
        if not subnet_result.ok or not isinstance(subnet_result.value, dict):
            checks.append(
                DiagnosticCheck(
                    id="subnet_vpc_validation",
                    status="fail",
                    message=subnet_result.message or "Unable to describe subnets via AWS CLI.",
                    action="Check subnet ids and IAM permissions for ec2:DescribeSubnets.",
                )
            )
        else:
            subnets = subnet_result.value.get("Subnets")
            if not isinstance(subnets, list) or len(subnets) != len(subnet_ids):
                checks.append(
                    DiagnosticCheck(
                        id="subnet_vpc_validation",
                        status="fail",
                        message="One or more provided subnets were not found.",
                        action="Verify subnet ids in the selected AWS region.",
                    )
                )
            else:
                vpc_ids: set[str] = set()
                azs: set[str] = set()
                for subnet in subnets:
                    if isinstance(subnet, dict):
                        subnet_vpc = _read_dict_string(subnet, "VpcId")
                        subnet_az = _read_dict_string(subnet, "AvailabilityZone")
                        if subnet_vpc:
                            vpc_ids.add(subnet_vpc)
                        if subnet_az:
                            azs.add(subnet_az)
                subnet_vpc_ok = len(vpc_ids) == 1 and (vpc_id is None or vpc_id in vpc_ids)
                multi_az_ok = len(azs) >= 2
                checks.append(
                    DiagnosticCheck(
                        id="subnet_vpc_validation",
                        status="pass" if subnet_vpc_ok and multi_az_ok else "fail",
                        message=(
                            "Subnets map to the selected VPC and span at least two availability zones."
                            if subnet_vpc_ok and multi_az_ok
                            else "Subnets must belong to the selected VPC and span at least two availability zones."
                        ),
                        action=(
                            None
                            if subnet_vpc_ok and multi_az_ok
                            else "Provide subnet ids in the same VPC across at least two AZs."
                        ),
                    )
                )

    if cli_ok and region and certificate_arn:
        cert_result = run_aws_json(
            ["acm", "describe-certificate", "--certificate-arn", certificate_arn, "--region", region]
        )
        if not cert_result.ok or not isinstance(cert_result.value, dict):
            checks.append(
                DiagnosticCheck(
                    id="acm_certificate_valid",
                    status="fail",
                    message=cert_result.message or "Unable to describe ACM certificate.",
                    action="Verify certificate ARN, region, and IAM permissions for acm:DescribeCertificate.",
                )
            )
        else:
            certificate_payload = cert_result.value.get("Certificate")
            status = None
            if isinstance(certificate_payload, dict):
                status = _read_dict_string(certificate_payload, "Status")
            checks.append(
                DiagnosticCheck(
                    id="acm_certificate_valid",
                    status="pass" if status == "ISSUED" else "fail",
                    message=(
                        f"ACM certificate status is {status}."
                        if status
                        else "ACM certificate status could not be read."
                    ),
                    action=(
                        None if status == "ISSUED" else "Use an ACM certificate ARN in ISSUED state for HTTPS listener."
                    ),
                )
            )

    details = AWSDoctorDetails(
        account_id=account_id,
        arn=arn,
        region=region,
        cluster_name=cluster_name,
        service_name=service_name,
        vpc_id=vpc_id,
        subnet_ids=subnet_ids,
        certificate_arn=certificate_arn,
        bucket_name=bucket_name,
    )
    return AWSDoctorEvaluation(
        ok=all(check.status != "fail" for check in checks),
        checks=tuple(checks),
        details=details,
    )


def _required_value_check(check_id: str, value: str | None, action: str) -> DiagnosticCheck:
    return DiagnosticCheck(
        id=check_id,
        status="pass" if value else "fail",
        message=f"Resolved value: {value}" if value else "Required value is missing.",
        action=None if value else action,
    )


def _resolve_subnets(*, explicit_value: str | None, configured: tuple[str, ...]) -> tuple[str, ...]:
    from_explicit = split_csv_values(explicit_value)
    if from_explicit:
        return from_explicit
    return tuple(value for value in configured if normalize_optional_text(value) is not None)


def _read_dict_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        normalized = normalize_optional_text(value)
        if normalized is not None:
            return normalized
    return None
