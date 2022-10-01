## Amazon EKS inter-az traffic visibility

The project implements an Amazon EKS Cross-AZ Pod to Pod network bytes visability
It is based on this (detailed) blog: [Link to Blog]

## Solution overview

Our solution is based on 2 boilerplates:

* An Amazon VPC and an Amazon EKS cluster.
* A Python based AWS CDK stack which implements an AWS Lambda Function, Amazon Athena Tables & Queries, and all other required resources and configurations.

![diagram](docs/diagram2.png)


Let's build...

### Prerequisites

* An AWS Account
* Shell environment with [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-getting-started.html) installed and Configured (e.g., [cloud9](https://aws.amazon.com/cloud9/))
* IAM role with policy permissions, that [deploys the Amazon EKS cluster](https://docs.aws.amazon.com/eks/latest/userguide/getting-started-eksctl.html), and the AWS CDK resources
* [Kubectl](https://docs.aws.amazon.com/eks/latest/userguide/install-kubectl.html)
* [Amazon EKS command line tool](https://docs.aws.amazon.com/eks/latest/userguide/eksctl.html) ([eksctl](https://eksctl.io/)), installed and configured
* Python3 and Node Package Manager (NPM)
* AWS CDK and its dependencies (provided in Step 2)
* [Amazon Athena query results Amazon S3 bucket](https://docs.aws.amazon.com/athena/latest/ug/querying.html#query-results-specify-location-console) (interactive execution)

### Step 1: Deploy an Amazon EKS Cluster

#### **Set the environment**

```
aws configure set region us-east-2
export AWS_REGION=$(aws configure get region ) && echo "Your region was set to: $AWS_REGION"
```

#### **Generate the ClusterConfig**

```
cat >cluster.yaml <<EOF
apiVersion: eksctl.io/v1alpha5
kind: ClusterConfig
metadata:
  name: cross-az
  region: ${AWS_REGION}
nodeGroups:
  - name: ng-1
    desiredCapacity: 2
EOF
```

#### Deploy the Cluster

```
eksctl create cluster -f cluster.yaml
```

#### Get the Worker nodes, Pods and their topology zone data

```
kubectl get nodes --label-columns topology.kubernetes.io/zone
```

Example output:

```
NAME                                           STATUS   ROLES    AGE   VERSION               ZONE
ip-192-168-51-15.us-east-2.compute.internal    Ready    <none>   20m   v1.22.9-eks-810597c   us-east-2b
ip-192-168-64-199.us-east-2.compute.internal   Ready    <none>   20m   v1.22.9-eks-810597c   us-east-2a
```

#### Clone the application repo

```
cd ~
git clone https://github.com/aws-samples/amazon-eks-inter-az-traffic-visibility
cd amazon-eks-inter-az-traffic-visibility
```

#### Deploy the demo application

```
cd kubernetes/demoapp/
kubectl apply -f .
```

Explore the demoapp YAMLs, the application consists of a single pod (i.e., http client) that runs a curl http loop on start. 
The target is a k8s service wired into 2 nginx server pods (Endpoints).
The server-dep k8s deployment is implementing [pod topology spread constrains](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/), spreading the pods across the distinct AZs.

#### Validate the demo application

```
kubectl get deployment
```

Example output:

```
NAME         READY   UP-TO-DATE   AVAILABLE   AGE
client-dep   1/1     1            1           14s
server-dep   2/2     2            2           14s
```

#### Validate that the server pods are spread across Nodes and AZs

```
kubectl get pods -l=app=server --sort-by="{.spec.nodeName}" -o wide
```

Example output:

```
NAME                         READY   STATUS    RESTARTS   AGE   IP               NODE                                           NOMINATED NODE   READINESS GATES
server-dep-797d7b54f-b9jf8   1/1     Running   0          61s   192.168.46.80    ip-192-168-51-15.us-east-2.compute.internal    <none>           <none>
server-dep-797d7b54f-8m6hx   1/1     Running   0          61s   192.168.89.235   ip-192-168-64-199.us-east-2.compute.internal   <none>           <none>
```

### Step 2: Deploy the CDK Stack

Create a Python virtual environment and install the dependencies

```
cd ~/amazon-eks-inter-az-traffic-visibility
python3 -m venv .venv
source .venv/bin/activate
./scripts/install-deps.sh
```

Our AWS CDK stack requires the VPC ID and the Amazon EKS cluster name

```
export CLUSTERNAME="cross-az"
export VPCID=$(aws eks describe-cluster --name $CLUSTERNAME --query cluster.resourcesVpcConfig.vpcId | sed -e 's/^"//' -e 's/"$//')
echo $CLUSTERNAME;echo $VPCID
```

#### Deploy the stack

```
npx cdk bootstrap
npx cdk deploy CdkEksInterAzVisibility --parameters eksClusterName=$CLUSTERNAME --parameters eksVpcId=$VPCID
```

#### Authorise the AWS Lambda function (k8s client)

Lets get the **Pod Metadata Extractor** **IAM Role** 
*(Used by the AWS Lambda function to authenticate and authorise when connecting to the Amazon EKS Cluster API.)*

```
export POD_METADATA_EXTRACTOR_IAM_ROLE=$(aws cloudformation describe-stacks --stack-name "CdkEksInterAzVisibility" --output json --query "Stacks[0].Outputs[0].OutputValue" | sed -e 's/^"//' -e 's/"$//')
echo $POD_METADATA_EXTRACTOR_IAM_ROLE
```

Create a ClusterRole and binding for the **Pod Metadata Extractor** AWS Lambda Function

```
kubectl apply -f kubernetes/pod-metadata-extractor-clusterrole.yaml
```

#### Append a role mapping to `ConfigMap/aws-auth`

>⚠ **We recommend using eksctl, or another tool, to edit the ConfigMap. For information about other tools you can use, see [Use tools](https://aws.github.io/aws-eks-best-practices/security/docs/iam/#use-tools-to-make-changes-to-the-aws-auth-configmap) to make changes to the aws-authConfigMap in the Amazon EKS best practices guides. An improperly formatted aws-auth ConfigMap can cause you to lose access to your cluster**

```
eksctl create iamidentitymapping \
--cluster ${CLUSTERNAME} \
--arn ${POD_METADATA_EXTRACTOR_IAM_ROLE} \
--username "eks-inter-az-visibility-binding" \
--group "eks-inter-az-visibility-group"
```

#### Validate

```
eksctl get iamidentitymapping --cluster ${CLUSTERNAME}
```

Expected output:

```
ARN                                                                                             USERNAME                                GROUPS                                  ACCOUNT
arn:aws:iam::555555555555:role/eksctl-cross-az-nodegroup-ng-1-NodeInstanceRole-IPHG3L5AXR3      system:node:{{EC2PrivateDNSName}}       system:bootstrappers,system:nodes
arn:aws:iam::555555555555:role/pod-metadata-extractor-role                                      eks-inter-az-visibility-binding         eks-inter-az-visibility-group
```

### Step 3: Viewing the process and results Interactively

* Head over to the [Amazon Athena](https://us-east-2.console.aws.amazon.com/athena/home?region=us-east-2#/query-editor) section.  
*(Query results bucket should have been set, see Prerequisites section. This should be a transient In-Region Amazon S3 bucket for the purpose of viewing the results, interactively)*
   
* On the Athena query pane, Start a new query (+ Sign) and run the below query:

```
SELECT * FROM "athena-results-table" ORDER BY "timestamp" DESC, "bytes_transfered";
```

Examine the results!

## Non-Interactive flow of the solution

The CDK stack will also deploy a step function workflow that will run the entire flow in a batch manner (hourly).
The flow is triggered using Amazon Event Bridge (see diagram).
This flow can be used if batch processing background flow is desired in cases you might wish to integrate with other platforms that will consume this data (Grafana, Prometheus)

## Considerations

* See full blog for detailed considerations

## Cleanup

### Destroy the CDK Stack

```
cd ~/amazon-eks-inter-az-traffic-visibility
source .venv/bin/activate
npx cdk destroy CdkEksInterAzVisibility
aws cloudformation delete-stack --stack-name CDKToolkit
```
If no longer needed, [delete the unneeded S3 buckets](https://docs.aws.amazon.com/AmazonS3/latest/userguide/delete-bucket.html)

### Destroy the EKS cluster

```
eksctl delete cluster --name=${CLUSTERNAME}
```

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

