import json
import boto3
import logging
import os
from urllib.parse import parse_qs

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
sqs = boto3.client("sqs")
dynamodb = boto3.resource("dynamodb")

# Configuration
QUEUE_URL = os.environ.get(
    "SQS_QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/071214564206/gpu-task-queue"
)
TABLE_NAME = os.environ.get("DYNAMO_TABLE_NAME", "PaperSummaries")
table = dynamodb.Table(TABLE_NAME)


def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
    }
    arxiv_obj = None

    # Extract body JSON
    if "body" in event and event["body"]:
        try:
            arxiv_obj = json.loads(event["body"])
        except json.JSONDecodeError:
            logger.error("Invalid JSON body")
            return {
                "statusCode": 400,
                "headers": cors_headers,
                "body": json.dumps({"error": "Invalid JSON"}),
            }

    if not arxiv_obj or "arxiv_id" not in arxiv_obj or "pdf_url" not in arxiv_obj:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "Missing arxiv_id or pdf_url"}),
        }

    arxiv_id = arxiv_obj["arxiv_id"]
    pdf_url = arxiv_obj["pdf_url"]
    task_id = context.aws_request_id

    # Check if item already exists
    try:
        response = table.get_item(Key={"arxiv_id": arxiv_id})
        item = response.get("Item")

        if item:
            logger.info(f"Found existing entry for arxiv_id: {arxiv_id}")
            if not item.get("processing", False) and not item.get("processing_error"):
                return {
                    "statusCode": 200,
                    "headers": cors_headers,
                    "body": json.dumps(item),
                }

            elif not item.get("processing", False) and item.get("processing_error"):
                logger.info(
                    f"Re-enqueueing arxiv_id {arxiv_id} due to error: {item['processing_error']}"
                )
                sqs.send_message(
                    QueueUrl=QUEUE_URL,
                    MessageBody=json.dumps(
                        {"arxiv_id": arxiv_id, "task_id": task_id, "pdf_url": pdf_url}
                    ),
                )
                return {
                    "statusCode": 200,
                    "headers": cors_headers,
                    "body": json.dumps(
                        {"message": "Re-enqueued for processing", "task_id": task_id}
                    ),
                }

            elif item.get("processing"):
                return {
                    "statusCode": 200,
                    "headers": cors_headers,
                    "body": json.dumps(
                        {
                            "message": "Task already queued",
                            "task_id": item.get("task_id"),
                        }
                    ),
                }

        else:
            logger.info(f"No entry found. Creating new entry for arxiv_id: {arxiv_id}")

            new_item = {
                "arxiv_id": arxiv_id,
                # 'hash_string': arxiv_obj.get('hash_string', ''),
                "processing": True,
                "task_id": task_id,
                "processing_error": "",
                "summary": arxiv_obj.get("summary", ""),
                "pdf_url": pdf_url,
                "manual_upload": False,
                "arxivReference": arxiv_obj,
            }

            table.put_item(Item=new_item)

            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(
                    {"arxiv_id": arxiv_id, "task_id": task_id, "pdf_url": pdf_url}
                ),
            )

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps(
                    {"message": "New task enqueued", "task_id": task_id}
                ),
            }

    except Exception as e:
        logger.error(f"Error accessing DynamoDB or sending SQS message: {str(e)}")
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": str(e)}),
        }
