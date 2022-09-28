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

from aws_cdk import aws_glue_alpha as glue_alpha

pod_table_columns = [
    glue_alpha.Column(name="name", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="ip", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="app", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="creation_time", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="node", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="labels", type=glue_alpha.Schema.STRING),
]

# ${az-id} ${flow-direction} ${pkt-srcaddr} ${pkt-dstaddr} ${start} ${bytes}
vpc_flow_logs_table_columns = [
    glue_alpha.Column(name="az_id", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="flow_direction", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="pkt_srcaddr", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="pkt_dstaddr", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="start", type=glue_alpha.Schema.BIG_INT),
    glue_alpha.Column(name="bytes", type=glue_alpha.Schema.BIG_INT),
]

athena_results_table_columns = [
    glue_alpha.Column(name="timestamp", type=glue_alpha.Schema.TIMESTAMP),
    glue_alpha.Column(name="cross_az_traffic", type=glue_alpha.Schema.STRING),
    glue_alpha.Column(name="bytes_transfered", type=glue_alpha.Schema.BIG_INT),
]
