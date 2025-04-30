#!/bin/bash

# Interactive script to deploy an AWS Lambda function with a created role

# Text formatting
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to get AWS account ID
get_account_id() {
  echo -e "${YELLOW}Fetching your AWS account ID...${NC}"
  ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
  
  if [ $? -ne 0 ]; then
    echo -e "${YELLOW}Could not automatically retrieve AWS account ID.${NC}"
    read -p "Please enter your AWS account ID: " ACCOUNT_ID
  else
    echo -e "${GREEN}Found AWS account ID: ${ACCOUNT_ID}${NC}"
    read -p "Is this correct? (Y/n): " confirm
    if [[ $confirm == [nN] ]]; then
      read -p "Please enter your AWS account ID: " ACCOUNT_ID
    fi
  fi
  
  # Validate account ID format (12 digits)
  while ! [[ $ACCOUNT_ID =~ ^[0-9]{12}$ ]]; do
    echo -e "${YELLOW}Invalid AWS account ID. It should be a 12-digit number.${NC}"
    read -p "Please enter your AWS account ID: " ACCOUNT_ID
  done
}

# Function to list zip files in current directory
list_zip_files() {
  echo -e "${BLUE}Available ZIP files in current directory:${NC}"
  ls -la *.zip 2>/dev/null
  
  if [ $? -ne 0 ]; then
    echo -e "${YELLOW}No ZIP files found in the current directory.${NC}"
  fi
}

# Welcome message
echo -e "${BOLD}=== AWS Lambda Deployment Tool ===${NC}"
echo "This script will help you deploy a Lambda function with a custom role."
echo ""

# Get AWS account ID
get_account_id

# Get AWS region
AWS_REGIONS=("us-east-1" "us-east-2" "us-west-1" "us-west-2" "eu-west-1" "eu-central-1" "ap-northeast-1" "ap-southeast-1" "ap-southeast-2")
echo -e "${BOLD}\nSelect AWS region:${NC}"
select REGION in "${AWS_REGIONS[@]}"; do
  if [ -n "$REGION" ]; then
    echo -e "Selected region: ${GREEN}$REGION${NC}"
    break
  else
    echo -e "${YELLOW}Invalid selection. Please try again.${NC}"
  fi
done

# Get Lambda function name
read -p $'\nEnter Lambda function name: ' FUNCTION_NAME
while [[ -z "$FUNCTION_NAME" ]]; do
  echo -e "${YELLOW}Function name cannot be empty.${NC}"
  read -p "Enter Lambda function name: " FUNCTION_NAME
done

# Get deployment ZIP file
list_zip_files
read -p $'\nEnter deployment ZIP file name (without .zip extension): ' ZIP_NAME
while [[ ! -f "${ZIP_NAME}.zip" ]]; do
  echo -e "${YELLOW}File ${ZIP_NAME}.zip not found.${NC}"
  list_zip_files
  read -p "Enter deployment ZIP file name (without .zip extension): " ZIP_NAME
done

# Get role name or generate one
read -p $'\nEnter IAM role name (leave empty to use function-name-role): ' ROLE_NAME
if [[ -z "$ROLE_NAME" ]]; then
  ROLE_NAME="${FUNCTION_NAME}-role"
  echo -e "Using default role name: ${GREEN}${ROLE_NAME}${NC}"
fi

# Get runtime
RUNTIMES=("python3.9" "python3.10" "python3.11" "nodejs18.x" "nodejs20.x" "java17" "dotnet6")
echo -e "${BOLD}\nSelect runtime:${NC}"
select RUNTIME in "${RUNTIMES[@]}"; do
  if [ -n "$RUNTIME" ]; then
    echo -e "Selected runtime: ${GREEN}$RUNTIME${NC}"
    break
  else
    echo -e "${YELLOW}Invalid selection. Please try again.${NC}"
  fi
done

# Get handler
if [[ $RUNTIME == python* ]]; then
  DEFAULT_HANDLER="lambda_function.lambda_handler"
elif [[ $RUNTIME == nodejs* ]]; then
  DEFAULT_HANDLER="index.handler"
else
  DEFAULT_HANDLER=""
fi

read -p $'\nEnter handler function (default: '"$DEFAULT_HANDLER"'): ' HANDLER
HANDLER=${HANDLER:-$DEFAULT_HANDLER}

# Get memory size
read -p $'\nEnter memory size in MB (default: 256): ' MEMORY_SIZE
MEMORY_SIZE=${MEMORY_SIZE:-256}

# Get timeout
read -p $'\nEnter timeout in seconds (default: 30): ' TIMEOUT
TIMEOUT=${TIMEOUT:-30}

# Review configuration
echo -e "\n${BOLD}=== Deployment Configuration ===${NC}"
echo -e "AWS Account ID: ${GREEN}$ACCOUNT_ID${NC}"
echo -e "AWS Region: ${GREEN}$REGION${NC}"
echo -e "Function name: ${GREEN}$FUNCTION_NAME${NC}"
echo -e "ZIP file: ${GREEN}${ZIP_NAME}.zip${NC}"
echo -e "IAM role name: ${GREEN}$ROLE_NAME${NC}"
echo -e "Runtime: ${GREEN}$RUNTIME${NC}"
echo -e "Handler: ${GREEN}$HANDLER${NC}"
echo -e "Memory size: ${GREEN}${MEMORY_SIZE} MB${NC}"
echo -e "Timeout: ${GREEN}${TIMEOUT} seconds${NC}"

# Confirmation
read -p $'\nProceed with deployment? (Y/n): ' confirm
if [[ $confirm == [nN] ]]; then
  echo -e "${YELLOW}Deployment cancelled.${NC}"
  exit 0
fi

echo -e "\n${BOLD}=== Starting Deployment ===${NC}"

# Create a trust policy document for the Lambda role
echo "Creating trust policy document..."
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Check if the role already exists
ROLE_EXISTS=$(aws iam get-role --role-name "$ROLE_NAME" 2>&1 || echo "ERROR")

if [[ "$ROLE_EXISTS" == *"ERROR"* ]]; then
  echo "Creating new IAM role: $ROLE_NAME"
  # Create the role
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document file://trust-policy.json

  # Attach the basic Lambda execution policy
  echo "Attaching Lambda basic execution policy..."
  aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

  # Wait for role to propagate
  echo "Waiting for role to propagate..."
  sleep 10
else
  echo "Role already exists: $ROLE_NAME"
fi

# Get the role ARN
ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"
echo "Using role ARN: $ROLE_ARN"

# Check if the Lambda function already exists
FUNCTION_EXISTS=$(aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" 2>&1 || echo "ERROR")

if [[ "$FUNCTION_EXISTS" == *"ERROR"* ]]; then
  # Create the Lambda function
  echo "Creating new Lambda function: $FUNCTION_NAME"
  RESULT=$(aws lambda create-function \
    --region "$REGION" \
    --function-name "$FUNCTION_NAME" \
    --runtime "$RUNTIME" \
    --handler "$HANDLER" \
    --timeout "$TIMEOUT" \
    --memory-size "$MEMORY_SIZE" \
    --zip-file "fileb://${ZIP_NAME}.zip" \
    --role "$ROLE_ARN" 2>&1)
  
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}Lambda function created successfully!${NC}"
  else
    echo -e "${YELLOW}Error creating Lambda function:${NC}"
    echo "$RESULT"
  fi
else
  # Update the Lambda function
  echo "Updating existing Lambda function: $FUNCTION_NAME"
  RESULT=$(aws lambda update-function-code \
    --region "$REGION" \
    --function-name "$FUNCTION_NAME" \
    --zip-file "fileb://${ZIP_NAME}.zip" 2>&1)
  
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}Lambda function updated successfully!${NC}"
  else
    echo -e "${YELLOW}Error updating Lambda function:${NC}"
    echo "$RESULT"
  fi
fi

# Clean up temporary files
rm -f trust-policy.json

echo -e "\n${BOLD}=== Deployment Complete ===${NC}"
echo -e "${GREEN}Function ARN: arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}${NC}"
echo ""
echo "You can test your Lambda function with:"
echo "aws lambda invoke --function-name $FUNCTION_NAME --payload '{\"path\": \"/health\", \"httpMethod\": \"GET\"}' response.json"