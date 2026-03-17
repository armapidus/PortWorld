from __future__ import annotations

import click

from portworld_cli.context import CLIContext
from portworld_cli.output import exit_with_result
from portworld_cli.services.doctor import DoctorOptions, run_doctor


@click.command("doctor")
@click.option(
    "--target",
    type=click.Choice(["local", "gcp-cloud-run", "aws-ecs-fargate"]),
    default="local",
    show_default=True,
    help="Readiness target to validate.",
)
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Run the storage bootstrap probe in addition to standard local checks.",
)
@click.option("--project", default=None, help="Target GCP project id for future gcp-cloud-run checks.")
@click.option("--region", default=None, help="Target GCP region for future gcp-cloud-run checks.")
@click.option("--aws-region", default=None, help="Target AWS region for aws-ecs-fargate checks.")
@click.option("--aws-cluster", default=None, help="Target ECS cluster name.")
@click.option("--aws-service", default=None, help="Target ECS service name.")
@click.option("--aws-vpc-id", default=None, help="Target VPC id.")
@click.option("--aws-subnet-ids", default=None, help="Target subnet ids (comma-separated).")
@click.option("--aws-certificate-arn", default=None, help="ACM certificate ARN for HTTPS listener.")
@click.option("--aws-database-url", default=None, help="Existing managed Postgres URL.")
@click.option("--aws-s3-bucket", default=None, help="S3 bucket name for managed artifacts.")
@click.pass_obj
def doctor_command(
    cli_context: CLIContext,
    target: str,
    full: bool,
    project: str | None,
    region: str | None,
    aws_region: str | None,
    aws_cluster: str | None,
    aws_service: str | None,
    aws_vpc_id: str | None,
    aws_subnet_ids: str | None,
    aws_certificate_arn: str | None,
    aws_database_url: str | None,
    aws_s3_bucket: str | None,
) -> None:
    """Validate local or managed deployment readiness."""
    exit_with_result(
        cli_context,
        run_doctor(
            cli_context,
            DoctorOptions(
                target=target,
                full=full,
                project=project,
                region=region,
                aws_region=aws_region,
                aws_cluster=aws_cluster,
                aws_service=aws_service,
                aws_vpc_id=aws_vpc_id,
                aws_subnet_ids=aws_subnet_ids,
                aws_certificate_arn=aws_certificate_arn,
                aws_database_url=aws_database_url,
                aws_s3_bucket=aws_s3_bucket,
            ),
        ),
    )
