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

INSERT INTO "{athena_results_table_name}"
WITH
ip_addresses_and_az_mapping AS (
SELECT DISTINCT pkt_srcaddr as ipaddress, az_id
FROM "{vpc_flow_logs_table_name}"
WHERE flow_direction = 'egress'
and from_unixtime("{vpc_flow_logs_table_name}".start)>(CURRENT_TIMESTAMP - ({invokation_frequency} * interval '1' minute))
),
egress_flows_of_pods_with_status AS (
SELECT
"{pods_table_name}".name as srcpodname,
"{pods_table_name}".app as srcpodapp,
pkt_srcaddr as srcaddr,
pkt_dstaddr as dstaddr,
"{vpc_flow_logs_table_name}".az_id as srcazid,
bytes, 
start
FROM "{vpc_flow_logs_table_name}"
INNER JOIN "{pods_table_name}" ON "{vpc_flow_logs_table_name}".pkt_srcaddr = "{pods_table_name}".ip
WHERE flow_direction = 'egress'
and from_unixtime("{vpc_flow_logs_table_name}".start)>(CURRENT_TIMESTAMP - ({invokation_frequency} * interval '1' minute))
),

cross_az_traffic_by_pod as (
SELECT
srcaddr,
srcpodname,
srcpodapp,
dstaddr,
"{pods_table_name}".name as dstpodname,
"{pods_table_name}".app as dstpodapp,
srcazid,
ip_addresses_and_az_mapping.az_id as dstazid,
bytes,
start
FROM egress_flows_of_pods_with_status
INNER JOIN "{pods_table_name}" ON dstaddr = "{pods_table_name}".ip
LEFT JOIN ip_addresses_and_az_mapping ON dstaddr = ipaddress
WHERE ip_addresses_and_az_mapping.az_id != srcazid
)

SELECT date_trunc('MINUTE', from_unixtime(start)) AS time, CONCAT(srcpodapp, ' -> ', dstpodapp) as inter_az_traffic, sum(bytes) as total_bytes
FROM cross_az_traffic_by_pod
WHERE srcpodapp!='<none>' AND dstpodapp!='<none>'
GROUP BY date_trunc('MINUTE', from_unixtime(start)), CONCAT(srcpodapp, ' -> ', dstpodapp)
ORDER BY time, total_bytes DESC