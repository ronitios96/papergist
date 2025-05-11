import json
import boto3
import logging
import os
from urllib.parse import parse_qs

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
sqs = boto3.client('sqs')
dynamodb = boto3.resource('dynamodb')

# Configuration
QUEUE_URL = os.environ.get('SQS_QUEUE_URL', 'https://sqs.us-east-1.amazonaws.com/071214564206/gpu-task-queue')
TABLE_NAME = os.environ.get('DYNAMO_TABLE_NAME', 'PaperSummaries')
table = dynamodb.Table(TABLE_NAME)

def generate_hash_string(text: str, char_limit: int = 100) -> str:
    """Generate a hash string from the first N characters of the text."""
    # Take first char_limit characters, remove spaces, newlines, and make lowercase
    if len(text) < char_limit:
        char_limit = len(text)
    
    # Remove both spaces and newline characters, then convert to lowercase
    clean_text = text[:char_limit].replace(" ", "").replace("\n", "").replace("\r", "").lower()
    logger.info(f"🔑 Generated hash string from first {char_limit} characters")
    return clean_text

def sanitize_arxiv_id(arxiv_id: str) -> str:
    """Remove '/' characters from arXiv ID to make it safe for URLs and DB keys."""
    return arxiv_id.replace("/", "-")

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    cors_headers = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'POST,OPTIONS,GET'  # Added GET to support paper endpoint
    }
    arxiv_obj = None

    # Handle OPTIONS method for CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers,
            'body': json.dumps({'message': 'CORS preflight successful'})
        }

    # Check if this is a "check_only" request
    check_only = False

    # Extract body JSON
    if 'body' in event and event['body']:
        try:
            arxiv_obj = json.loads(event['body'])
            check_only = arxiv_obj.get('check_only', False)
        except json.JSONDecodeError:
            logger.error("Invalid JSON body")
            return {'statusCode': 400, 'headers': cors_headers, 'body': json.dumps({'error': 'Invalid JSON'})}

    if not arxiv_obj or 'arxiv_id' not in arxiv_obj:
        return {'statusCode': 400, 'headers': cors_headers, 'body': json.dumps({'error': 'Missing arxiv_id'})}

    # Sanitize the arXiv ID by removing '/' characters
    original_arxiv_id = arxiv_obj['arxiv_id']
    arxiv_id = sanitize_arxiv_id(original_arxiv_id)
    pdf_url = arxiv_obj.get('pdf_url', '')
    task_id = context.aws_request_id
    
    # Generate hash string from summary if available
    summary = arxiv_obj.get('summary', '')
    hash_string = "not_set_yet"#generate_hash_string(summary) if summary else 'nosummary'

    # Check if item already exists
    try:
        response = table.get_item(Key={'arxiv_id': arxiv_id})
        item = response.get('Item')
        
        if item:
            logger.info(f"Found existing entry for arxiv_id: {arxiv_id}")
            
            # If check_only is True, return the existing item with additional metadata
            if check_only:
                return {
                    'statusCode': 200, 
                    'headers': cors_headers, 
                    'body': json.dumps({
                        **item,
                        'exists': True,
                        'processing': item.get('processing', False)
                    })
                }
            
            # If already summarized, return the summary
            if not item.get('processing', False) and not item.get('processing_error'):
                return {'statusCode': 200, 'headers': cors_headers, 'body': json.dumps(item)}

            # If processing error, re-enqueue
            elif not item.get('processing', False) and item.get('processing_error'):
                # Don't re-enqueue if this is just a check
                if check_only:
                    return {
                        'statusCode': 200,
                        'headers': cors_headers,
                        'body': json.dumps({
                            'exists': True,
                            'processing': False,
                            'processing_error': item.get('processing_error', ''),
                            'message': 'Previous processing error'
                        })
                    }
                
                logger.info(f"Re-enqueueing arxiv_id {arxiv_id} due to error: {item['processing_error']}")
                sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({
                    'arxiv_id': arxiv_id,
                    'task_id': task_id,
                    'pdf_url': pdf_url
                }))
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({'message': 'Re-enqueued for processing', 'task_id': task_id})
                }

            # If currently processing
            elif item.get('processing'):
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({
                        'message': 'Task already queued', 
                        'task_id': item.get('task_id'),
                        'exists': True,
                        'processing': True
                    })
                }

        else:
            logger.info(f"No entry found. Creating new entry for arxiv_id: {arxiv_id}")
            
            # If check_only is True, just return that it doesn't exist
            if check_only:
                return {
                    'statusCode': 200,
                    'headers': cors_headers,
                    'body': json.dumps({
                        'exists': False,
                        'processing': False,
                        'message': 'No entry found for this arXiv ID'
                    })
                }

            # For ensuring the original arXiv ID is preserved in the reference
            if 'arxiv_id' in arxiv_obj:
                arxiv_obj['original_arxiv_id'] = arxiv_obj['arxiv_id']
                arxiv_obj['arxiv_id'] = arxiv_id

            new_item = {
                'arxiv_id': arxiv_id,
                'hash_string': hash_string,  # Using the generated hash string
                'processing': True,
                'task_id': task_id,
                'processing_error': '',
                'summary': '',
                'pdf_url': pdf_url,
                'manual_upload': False,
                'arxivReference': arxiv_obj
            }

            table.put_item(Item=new_item)

            sqs.send_message(QueueUrl=QUEUE_URL, MessageBody=json.dumps({
                'arxiv_id': arxiv_id,
                'task_id': task_id,
                'pdf_url': pdf_url
            }))

            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({'message': 'New task enqueued', 'task_id': task_id})
            }

    except Exception as e:
        logger.error(f"Error accessing DynamoDB or sending SQS message: {str(e)}")
        return {'statusCode': 500, 'headers': cors_headers, 'body': json.dumps({'error': str(e)})}
