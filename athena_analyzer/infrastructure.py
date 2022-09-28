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
from aws_cdk import aws_athena as athena
from aws_cdk import aws_glue as glue
from aws_cdk import aws_glue_alpha as glue_alpha
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from constructs import Construct

from .glue_tables_columns import athena_results_table_columns
from .glue_tables_columns import pod_table_columns
from .glue_tables_columns import vpc_flow_logs_table_columns


class AthenaAnalyzer(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        pod_metadata_extractor_bucket: s3.Bucket,
        flow_logs_bucket: s3.Bucket,
        frequency: Duration,
        server_access_logs_bucket: s3.Bucket,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.results_bucket = self.__create_results_bucket(server_access_logs_bucket)

        self.glue_database = self.__create_glue_catalog_database()
        self.__set_glue_data_catalog_encryption(self.glue_database.catalog_id)

        pods_table = self.__create_pods_table(
            pod_metadata_extractor_bucket, self.glue_database
        )
        flow_logs_table = self.__create_flow_logs_table(
            flow_logs_bucket, self.glue_database
        )
        athena_results_table = self.__create_results_table(
            self.glue_database, self.results_bucket
        )

        self.sql_query_string = self.__create_athena_named_query(
            self.glue_database,
            pods_table,
            flow_logs_table,
            athena_results_table,
            frequency,
        )

    def __set_glue_data_catalog_encryption(self, catalog_id: str) -> None:
        encryption_at_rest_settings = (
            glue.CfnDataCatalogEncryptionSettings.EncryptionAtRestProperty(
                catalog_encryption_mode="SSE-KMS",
            )
        )

        encryption_settings = (
            glue.CfnDataCatalogEncryptionSettings.DataCatalogEncryptionSettingsProperty(
                encryption_at_rest=encryption_at_rest_settings
            )
        )

        glue.CfnDataCatalogEncryptionSettings(
            self,
            "Glue-Data-Catalog-Encryption",
            catalog_id=catalog_id,
            data_catalog_encryption_settings=encryption_settings,
        )

    def __create_results_bucket(self, server_access_logs_bucket) -> s3.Bucket:
        bucket = s3.Bucket(
            self,
            "athena-results",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            server_access_logs_bucket=server_access_logs_bucket,
        )
        return bucket

    def __create_glue_catalog_database(self) -> glue_alpha.Database:
        glue_database = glue_alpha.Database(
            self,
            "eks-inter-az-visibility-database",
            database_name="eks-inter-az-visibility",
        )
        return glue_database

    def __create_pods_table(
        self,
        pod_metadata_extractor_bucket: s3.Bucket,
        glue_database: glue_alpha.Database,
    ) -> glue_alpha.Table:
        pods_table = glue_alpha.Table(
            self,
            "pods-table",
            table_name="pods-table",
            database=glue_database,
            columns=pod_table_columns,
            data_format=glue_alpha.DataFormat.CSV,
            bucket=pod_metadata_extractor_bucket,
        )
        return pods_table

    def __create_flow_logs_table(
        self, flow_logs_bucket: s3.Bucket, glue_database: glue_alpha.Database
    ) -> glue_alpha.Table:
        flow_logs_table = glue_alpha.Table(
            self,
            "flow-logs-table",
            table_name="vpc-flow-logs-table",
            database=glue_database,
            columns=vpc_flow_logs_table_columns,
            data_format=glue_alpha.DataFormat.PARQUET,
            bucket=flow_logs_bucket,
        )
        return flow_logs_table

    def __create_results_table(
        self, glue_database: glue_alpha.Database, bucket: s3.Bucket
    ) -> glue_alpha.Table:
        athena_results_table = glue_alpha.Table(
            self,
            "athena-results-table",
            table_name="athena-results-table",
            database=glue_database,
            columns=athena_results_table_columns,
            data_format=glue_alpha.DataFormat.PARQUET,
            bucket=bucket,
            s3_prefix="inter-az-traffic",
        )
        return athena_results_table

    def __create_athena_named_query(
        self,
        glue_database: glue_alpha.Database,
        pods_table: glue_alpha.Table,
        flow_logs_table: glue_alpha.Table,
        athena_results_table: glue_alpha.Table,
        frequency: Duration,
    ) -> athena.CfnNamedQuery:
        query_cross_az_traffic_by_app_path = self.__get_query_template_file_path()

        query_cross_az_traffic_by_app = self.__get_formatted_query(
            pods_table,
            flow_logs_table,
            athena_results_table,
            query_cross_az_traffic_by_app_path,
            frequency,
        )

        query = athena.CfnNamedQuery(
            self,
            "query-cross-az-traffic-by-app",
            name="query-cross-az-traffic-by-app",
            database=glue_database.database_name,
            query_string=query_cross_az_traffic_by_app,
            description="Joins VPC Flow Logs and pod-metadata-extractor results to gain visibility of inter-az traffic between pods in an EKS cluster",
        )

        return query.query_string

    def __get_query_template_file_path(self) -> str:
        queries_dir_path = str(
            pathlib.Path(__file__).parent.joinpath("queries").resolve()
        )
        query_cross_az_traffic_by_app_path = (
            f"{queries_dir_path}/cross_az_traffic_by_app.sql"
        )
        return query_cross_az_traffic_by_app_path

    def __get_formatted_query(
        self,
        pods_table: glue_alpha.Table,
        flow_logs_table: glue_alpha.Table,
        athena_results_table: glue_alpha.Table,
        query_cross_az_traffic_by_app_path: str,
        invokation_frequency: Duration,
    ) -> str:
        query_cross_az_traffic_by_app = ""

        with open(query_cross_az_traffic_by_app_path, "r") as file:
            for line in file:
                # Skip comment-lines that start with '#'
                if line.startswith("#"):
                    continue
                query_cross_az_traffic_by_app += line

        query_cross_az_traffic_by_app = query_cross_az_traffic_by_app.format(
            athena_results_table_name=athena_results_table.table_name,
            pods_table_name=pods_table.table_name,
            vpc_flow_logs_table_name=flow_logs_table.table_name,
            invokation_frequency=invokation_frequency.to_minutes(),
        )

        return query_cross_az_traffic_by_app
