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

import pathlib
from typing import Any

from aws_cdk import Duration
from aws_cdk import RemovalPolicy
from aws_cdk import Stack
from aws_cdk import aws_eks as eks
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import lambda_layer_awscli
from constructs import Construct

APP_LABEL = "app"
COMPONENT_LABEL = "component"


class PodMetaDataExtractor(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        eks_cluster: eks.Cluster,
        server_access_logs_bucket: s3.Bucket,
        **kwargs: Any
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.bucket = self.__create_pod_state_bucket(server_access_logs_bucket)

        self.lambda_k8s_client = self.__create_pod_metadata_extractor_lambda_function(
            eks_cluster, self.bucket
        )
        self.bucket.grant_write(self.lambda_k8s_client)

        self.eks_client_role = self.__create_k8s_client_iam_role(
            eks_cluster, self.lambda_k8s_client.role
        )
        self.__add_iam_policies_to_lambda_function(
            eks_cluster, self.lambda_k8s_client, self.eks_client_role
        )

        self.lambda_k8s_client.add_environment(
            "K8S_CLIENT_ROLE_ARN", self.eks_client_role.role_arn
        )

    def __create_pod_state_bucket(self, server_access_logs_bucket) -> s3.Bucket:
        """
        Creates an S3 bucket where the Lambda Function will store pod states.
        """
        bucket = s3.Bucket(
            self,
            "pod-state-bucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            server_access_logs_bucket=server_access_logs_bucket,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,
        )
        return bucket

    def __create_pod_metadata_extractor_lambda_function(
        self, eks_cluster: eks.Cluster, bucket: s3.Bucket
    ) -> lambda_.Function:
        """
        Creates a Lambda Function that acts as a K8S Client.
        This Lambda Function will get all the pods' states and store them in an S3 Bucket.
        """

        python_lambda_layers = self.__create_dependencies_lambda_layer()

        lambda_function = lambda_.Function(
            self,
            "pod-state-extractor-lambda-function",
            function_name="pod_metadata_extractor",
            description="Extracts the current pod-state in an EKS cluster",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset(
                str(pathlib.Path(__file__).parent.joinpath("runtime").resolve())
            ),
            handler="get_pods.lambda_handler",
            timeout=Duration.minutes(1),
            environment={
                "REGION": Stack.of(self).region,
                "CLUSTER_NAME": eks_cluster.cluster_name,
                "APP_LABEL": APP_LABEL,
                "COMPONENT_LABEL": COMPONENT_LABEL,
                "OUTPUT_BUCKET_NAME": bucket.bucket_name,
                "CURRENT_ACCOUNT_ID": Stack.of(self).account,
            },
            layers=python_lambda_layers,
            tracing=lambda_.Tracing.ACTIVE,
        )
        return lambda_function

    def __create_dependencies_lambda_layer(self) -> lambda_.LayerVersion:
        """
        Creates a Lambda Layer that has the dependencies for our Lambda Function.
        The dependencies are stored in the `./runtime/requirements.in` file.
        """

        aws_cli_layer = lambda_layer_awscli.AwsCliLayer(self, "Aws-Cli-Lambda-Layer")

        python_k8s_client_lambda_layer = lambda_.LayerVersion(
            self,
            "layer-python-k8s-client",
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_9],
            code=lambda_.Code.from_asset(
                str(
                    pathlib.Path(__file__)
                    .parent.joinpath("requirements_layer")
                    .resolve()
                )
            ),
            removal_policy=RemovalPolicy.DESTROY,
        )
        return [aws_cli_layer, python_k8s_client_lambda_layer]

    def __create_k8s_client_iam_role(
        self, eks_cluster: eks.Cluster, lambda_role: iam.Role
    ) -> iam.Role:
        """
        Creates the IAM Role the Lambda Function would assume to act as a k8s client.
        This IAM role shuold be mapped to a K8S ClusterRole in the aws-auth ConfigMap.
        """
        role = iam.Role(
            self,
            "eks-inter-az-visibility-extractor-role",
            role_name="pod-metadata-extractor-role",
            description="An IAM role for the pod-metadata-extractor Lambda Function to assume for quering the K8S API ",
            assumed_by=iam.ArnPrincipal(lambda_role.role_arn),
            inline_policies={
                "allow-describe-cluster": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["eks:DescribeCluster"],
                            effect=iam.Effect.ALLOW,
                            resources=[eks_cluster.cluster_arn],
                        ),
                    ]
                )
            },
        )
        return role

    def __add_iam_policies_to_lambda_function(
        self,
        eks_cluster: eks.Cluster,
        lambda_function: lambda_.Function,
        eks_client_role: iam.Role,
    ) -> None:
        """
        Adds necessary IAM policies to the Lambda Function's IAM Role.
        """
        # Allow lambda to assume k8s client role
        lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["sts:AssumeRole"],
                effect=iam.Effect.ALLOW,
                resources=[eks_client_role.role_arn],
            )
        )

        # Allow lambda to describe the EKS cluster
        lambda_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["eks:DescribeCluster"],
                effect=iam.Effect.ALLOW,
                resources=[eks_cluster.cluster_arn],
            )
        )
