# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from aws_cdk import Duration
from aws_cdk import RemovalPolicy
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_s3 as s3
from constructs import Construct

FLOW_LOGS_FORMAT = (
    "${az-id} ${flow-direction} ${pkt-srcaddr} ${pkt-dstaddr} ${start} ${bytes}"
)


class VPCFlowLogs(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        vpc: ec2.Vpc,
        server_access_logs_bucket: s3.Bucket,
        **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.bucket = self.__create_flow_logs_bucket(server_access_logs_bucket)
        self.__create_flow_logs_for_vpc(vpc, self.bucket)

    def __create_flow_logs_for_vpc(
        self, vpc: ec2.Vpc, destination_bucket: s3.Bucket
    ) -> None:
        """
        Adds Flow Logs to a VPC. The Flow Logs are sent to the destination S3 Bucket.
        """
        flow_logs = ec2.CfnFlowLog(
            self,
            "eks-inter-az-visibility-s3-flow-logs",
            resource_id=vpc.vpc_id,
            resource_type="VPC",
            traffic_type="ALL",
            log_destination_type="s3",
            log_destination=destination_bucket.bucket_arn,
            destination_options={
                "FileFormat": "parquet",
                "HiveCompatiblePartitions": False,
                "PerHourPartition": True,
            },
            log_format=FLOW_LOGS_FORMAT,
        )
        flow_logs.node.add_dependency(destination_bucket)

    def __create_flow_logs_bucket(self, server_access_logs_bucket) -> s3.Bucket:
        """
        Creates an S3 Bucket where the VPC Flow Logs will be sent to.
        """
        bucket = s3.Bucket(
            self,
            "vpc-flow-logs-bucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            lifecycle_rules=[
                s3.LifecycleRule(enabled=True, expiration=Duration.days(1))
            ],
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            server_access_logs_bucket=server_access_logs_bucket,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
        )
        return bucket
