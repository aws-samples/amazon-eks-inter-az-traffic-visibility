#!/bin/bash

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
set -e


export AWS_REGION=$(aws configure get region) && echo "Your region was set to: $AWS_REGION"
export CLUSTERNAME="cross-az"
export VERSION="1.31"

cat >cluster.yaml <<EOF
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: cross-az
  region: "${AWS_REGION}"
  version: "${VERSION}"
nodeGroups:
  - name: ng-1
    desiredCapacity: 2
EOF

eksctl create cluster -f cluster.yaml || echo "A cluster named ${CLUSTERNAME} already exists, skipping..."

kubectl apply -f ./kubernetes/demoapp/

python3 -m venv .venv
source .venv/bin/activate
./scripts/install-deps.sh

export VPCID=$(aws eks describe-cluster --name $CLUSTERNAME --query cluster.resourcesVpcConfig.vpcId | sed -e 's/^"//' -e 's/"$//')
echo $CLUSTERNAME;echo $VPCID 

npx cdk deploy CdkEksInterAzVisibility --parameters eksClusterName=$CLUSTERNAME --parameters eksVpcId=$VPCID --require-approval never

export POD_METADATA_EXTRACTOR_IAM_ROLE=$(aws cloudformation describe-stacks --stack-name "CdkEksInterAzVisibility" --output json --query "Stacks[0].Outputs[0].OutputValue" | sed -e 's/^"//' -e 's/"$//')
echo $POD_METADATA_EXTRACTOR_IAM_ROLE

kubectl apply -f kubernetes/pod-metadata-extractor-clusterrole.yaml

eksctl create iamidentitymapping \
--cluster ${CLUSTERNAME} \
--arn ${POD_METADATA_EXTRACTOR_IAM_ROLE} \
--username "eks-inter-az-visibility-binding" \
--group "eks-inter-az-visibility-group"
