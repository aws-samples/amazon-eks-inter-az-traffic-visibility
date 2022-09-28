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

from aws_cdk import RemovalPolicy
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as stepfunctions
from aws_cdk import aws_stepfunctions_tasks as stepfunctions_tasks
from constructs import Construct

from athena_analyzer.infrastructure import AthenaAnalyzer


class OrchestratorStepFunction(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        pod_metadata_extractor_lambda_function: lambda_.Function,
        athena_analyzer: AthenaAnalyzer,
        **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        invoke_pod_metadata_extractor_state = (
            self.__create_invoke_pod_metadata_extractor_state(
                pod_metadata_extractor_lambda_function
            )
        )
        start_athena_query_state = self.__create_start_athena_query_state(
            athena_analyzer
        )

        state_machine_definition = self.__create_state_machine_definition(
            invoke_pod_metadata_extractor_state, start_athena_query_state
        )
        self.state_machine = self.__create_state_machine(state_machine_definition)

        athena_analyzer.results_bucket.grant_put(self.state_machine)

    def __create_state_machine(
        self, state_machine_definition: stepfunctions.Chain
    ) -> stepfunctions.StateMachine:
        """
        Creates a StepFunction StateMachine that orchestrates running of the inter-az traffic analysis
        """
        log_group = self.__create_log_group()
        logs_option = stepfunctions.LogOptions(
            destination=log_group,
            include_execution_data=True,
            level=stepfunctions.LogLevel.ALL,
        )

        state_machine = stepfunctions.StateMachine(
            self,
            id="State-Machine",
            definition=state_machine_definition,
            state_machine_name="pod-metadata-extractor-orchestrator",
            logs=logs_option,
            tracing_enabled=True,
        )
        log_group.grant_write(state_machine)

        return state_machine

    def __create_log_group(self):
        log_group = logs.LogGroup(
            self,
            "State-Machine-Log-Group",
            log_group_name="Orchestrator-Log-Group",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_DAY,
        )
        return log_group

    def __create_state_machine_definition(
        self,
        invoke_pod_metadata_extractor_state: stepfunctions_tasks.LambdaInvoke,
        start_athena_query_state: stepfunctions_tasks.AthenaStartQueryExecution,
    ) -> stepfunctions.Chain:
        """
        Creates a definition of the flow for a StepFunction StateMachine
        """
        fail_state = stepfunctions.Fail(self, "Fail-State")
        choice_state = stepfunctions.Choice(self, "Check-Statue-Code")

        http_success_condition = stepfunctions.Condition.number_equals(
            "$.Payload.statusCode", 200
        )

        state_machine_definition = invoke_pod_metadata_extractor_state.next(
            choice_state.when(
                http_success_condition, start_athena_query_state
            ).otherwise(fail_state)
        )

        return state_machine_definition

    def __create_start_athena_query_state(
        self, athena_analyzer: AthenaAnalyzer
    ) -> stepfunctions_tasks.AthenaStartQueryExecution:
        """
        Creates a StepFunction task that starts the inter-az traffic Athena Query
        """
        query_execution_context = stepfunctions_tasks.QueryExecutionContext(
            database_name=athena_analyzer.glue_database.database_name
        )

        result_configuration = stepfunctions_tasks.ResultConfiguration(
            output_location=s3.Location(
                bucket_name=athena_analyzer.results_bucket.bucket_name,
                object_key="query_results",
            )
        )

        start_athena_query_state = stepfunctions_tasks.AthenaStartQueryExecution(
            self,
            id="Start-Athena-Query",
            query_string=athena_analyzer.sql_query_string,
            query_execution_context=query_execution_context,
            result_configuration=result_configuration,
        )

        return start_athena_query_state

    def __create_invoke_pod_metadata_extractor_state(
        self, pod_metadata_extractor_lambda_function: lambda_.Function
    ) -> stepfunctions_tasks.LambdaInvoke:
        """
        Creates a StepFunction task that invokes the pod_metadata_extractor lambda function
        """
        invoke_pod_metadata_extractor_state = stepfunctions_tasks.LambdaInvoke(
            self,
            id="Invoke-Pod-Metadata-Extractor-Lambda-Function",
            lambda_function=pod_metadata_extractor_lambda_function,
        )

        return invoke_pod_metadata_extractor_state
