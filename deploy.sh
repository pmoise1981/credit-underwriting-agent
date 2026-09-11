#!/usr/bin/env bash
# Full deploy sequence. Requires: AWS CLI configured, Docker running, Terraform installed.
set -euo pipefail

cd "$(dirname "$0")"

echo "== 1/4: Provisioning ECR repo =="
cd terraform
terraform init
terraform apply -target=aws_ecr_repository.app -auto-approve
ECR_URL=$(terraform output -raw ecr_repository_url)
cd ..

echo "== 2/4: Building and pushing container image =="
docker buildx build --provenance=false --sbom=false -t underwriting-agent --load .
aws ecr get-login-password --region "${AWS_REGION:-us-east-1}" | docker login --username AWS --password-stdin "${ECR_URL%%/*}"
docker tag underwriting-agent:latest "${ECR_URL}:latest"
docker push "${ECR_URL}:latest"

echo "== 3/4: Applying remaining infra (DynamoDB tables, IAM, Lambda, function URL) =="
cd terraform
terraform apply -auto-approve
LAMBDA_URL=$(terraform output -raw lambda_url)
cd ..

echo "== 4/4: Seeding synthetic test data =="
python data_seed.py

echo ""
echo "Done. Lambda URL: ${LAMBDA_URL}"
echo "Test with:"
echo "curl -X POST ${LAMBDA_URL} --aws-sigv4 \"aws:amz:${AWS_REGION:-us-east-1}:lambda\" --user \"\$(aws configure get aws_access_key_id):\$(aws configure get aws_secret_access_key)\" -H \"Content-Type: application/json\" -d '{\"applicant_id\": \"APP-1001\"}'"
