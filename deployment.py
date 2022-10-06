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

from aws_cdk import CfnOutput
from aws_cdk import CfnParameter
from aws_cdk import Duration
from aws_cdk import RemovalPolicy
from aws_cdk import Stack
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_eks as eks
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as events_targets
from aws_cdk import aws_s3 as s3
from constructs import Construct

from athena_analyzer.infrastructure import AthenaAnalyzer
from orchestrator_step_function.infrastructure import OrchestratorStepFunction
from pod_metadata_extractor.infrastructure import PodMetaDataExtractor
from vpc_flow_logs.infrastructure import VPCFlowLogs

EVENT_BRIDGE_SCHEDULED_RULE_FREQUENCY = Duration.minutes(60)


class EksInterAzVisibility(Stack):
    def __init__(self, scope: Construct, id_: str, **kwargs) -> None:
        super().__init__(scope, id_, **kwargs)

        eks_cluster = self.__get_eks_cluster_from_parameter()
        eks_vpc = self.__get_vpc_from_parameter()

        server_access_logs_bucket = self.create_server_access_logs_bucket()

        pod_metadata_extractor = PodMetaDataExtractor(
            scope=self,
            id="PodMetaDataExtractor",
            eks_cluster=eks_cluster,
            server_access_logs_bucket=server_access_logs_bucket,
        )

        vpc_flow_logs = VPCFlowLogs(
            scope=self,
            id="FlowLogs",
            vpc=eks_vpc,
            server_access_logs_bucket=server_access_logs_bucket,
        )

        athena_analyzer = AthenaAnalyzer(
            scope=self,
            id="AthenaAnalyzer",
            pod_metadata_extractor_bucket=pod_metadata_extractor.bucket,
            flow_logs_bucket=vpc_flow_logs.bucket,
            frequency=EVENT_BRIDGE_SCHEDULED_RULE_FREQUENCY,
            server_access_logs_bucket=server_access_logs_bucket,
        )

        orchestrator = OrchestratorStepFunction(
            scope=self,
            id="OrchestratorStepFunction",
            pod_metadata_extractor_lambda_function=pod_metadata_extractor.lambda_k8s_client,
            athena_analyzer=athena_analyzer,
        )

        self.create_event_bridge_scheduled_rule(
            orchestrator, EVENT_BRIDGE_SCHEDULED_RULE_FREQUENCY
        )

        CfnOutput(
            self,
            "Lambda-K8S-Client-Role-ARN",
            value=pod_metadata_extractor.eks_client_role.role_arn,
        )

    def create_server_access_logs_bucket(self):
        server_access_logs_bucket = s3.Bucket(
            self,
            "Server-Access-Logs",
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
        )

        return server_access_logs_bucket

    def create_event_bridge_scheduled_rule(
        self, orchestrator: OrchestratorStepFunction, frequency: Duration
    ):
        return events.Rule(
            scope=self,
            id="Scheduled-Rule",
            schedule=events.Schedule.rate(frequency),
            targets=[events_targets.SfnStateMachine(orchestrator.state_machine)],
        )

    def __get_vpc_from_parameter(self):
        eks_cluster_vpc_id = CfnParameter(
            self,
            "eksVpcId",
            type="String",
            description="The ID of the VPC the EKS cluster is in.",
        )

        eks_vpc = ec2.Vpc.from_vpc_attributes(
            self,
            "eks-vpc",
            availability_zones=Stack.of(self).availability_zones,
            vpc_id=eks_cluster_vpc_id.value_as_string,
        )

        return eks_vpc

    def __get_eks_cluster_from_parameter(self):
        eks_cluster_name = CfnParameter(
            self,
            "eksClusterName",
            type="String",
            description="The name of the EKS cluster to plug into.",
        )

        eks_cluster = eks.Cluster.from_cluster_attributes(
            self,
            "eks-cluster",
            cluster_name=eks_cluster_name.value_as_string,
        )

        return eks_cluster
