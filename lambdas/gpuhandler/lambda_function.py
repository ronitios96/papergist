import json
import boto3
import logging
import time
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
sqs = boto3.client('sqs')
ec2 = boto3.client('ec2')

# Get queue URL from environment variable
SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL', 'https://sqs.us-east-1.amazonaws.com/071214564206/gpu-task-queue')
# GPU instance ID - must be set in Lambda environment variables
GPU_INSTANCE_ID = os.environ.get('GPU_INSTANCE_ID', 'i-009ef9d52f4bb8756')
# EC2 endpoint URL for the GPU service
GPU_SERVICE_URL = os.environ.get('GPU_SERVICE_URL', '')
# Maximum polling time in seconds
MAX_POLLING_TIME = 300

def lambda_handler(event, context):
    """
    Lambda function that processes SQS messages and manages GPU instance.
    
    This function:
    1. Checks if there are messages in the queue
    2. If yes, ensures the GPU instance is running
    3. Lets the GPU instance process the messages
    """
    logger.info("Processing SQS event trigger")
    
    # Check if there are messages in the queue
    try:
        queue_attributes = sqs.get_queue_attributes(
            QueueUrl=SQS_QUEUE_URL,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        
        message_count = int(queue_attributes['Attributes']['ApproximateNumberOfMessages'])
        logger.info(f"Approximate number of messages in queue: {message_count}")
        
        # If no messages, nothing to do
        if message_count == 0:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No messages in queue'
                })
            }
            
        # Validate GPU instance ID is set
        if not GPU_INSTANCE_ID:
            logger.error("GPU_INSTANCE_ID environment variable not set")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'error': 'GPU_INSTANCE_ID environment variable not set'
                })
            }
            
        # Check GPU instance state and start if needed
        instance_state = get_instance_state(GPU_INSTANCE_ID)
        logger.info(f"Current GPU instance state: {instance_state}")
        
        # If instance is stopped or stopping, start it
        if instance_state in ['stopped', 'stopping']:
            logger.info(f"Starting GPU instance {GPU_INSTANCE_ID}")
            ec2.start_instances(InstanceIds=[GPU_INSTANCE_ID])
            
            # Wait for instance to start and service to be ready
            wait_for_instance_and_service(GPU_INSTANCE_ID)
            
        # If instance is already running, just ensure service is ready
        elif instance_state == 'running':
            # Simple check to see if service is responding
            ensure_service_ready()
            
        # For any other state (pending, etc.), just log and wait
        else:
            logger.info(f"Instance is in {instance_state} state. No action taken.")
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'GPU instance {GPU_INSTANCE_ID} is processing tasks',
                'instanceState': get_instance_state(GPU_INSTANCE_ID)
            })
        }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def get_instance_state(instance_id):
    """Get the current state of an EC2 instance"""
    response = ec2.describe_instances(InstanceIds=[instance_id])
    
    # Extract instance state
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            return instance['State']['Name']
    
    return 'unknown'

def wait_for_instance_and_service(instance_id):
    """Wait for instance to be in running state and service to be ready"""
    # First wait for instance to be running
    logger.info("Waiting for instance to be in running state")
    
    start_time = time.time()
    current_state = get_instance_state(instance_id)
    
    while current_state != 'running':
        # Check if we've exceeded maximum polling time
        if time.time() - start_time > MAX_POLLING_TIME:
            logger.warning(f"Timed out waiting for instance to start. Current state: {current_state}")
            break
            
        logger.info(f"Instance state: {current_state}, waiting...")
        time.sleep(10)
        current_state = get_instance_state(instance_id)
    
    # Then ensure service is ready
    if current_state == 'running':
        logger.info("Instance is running. Ensuring service is ready.")
        ensure_service_ready()
    
def ensure_service_ready():
    """Ensure the GPU service is ready to accept tasks"""
    if not GPU_SERVICE_URL:
        logger.warning("GPU_SERVICE_URL environment variable not set, cannot check service readiness")
        return
        
    import requests
    
    logger.info(f"Checking if service at {GPU_SERVICE_URL} is ready")
    
    start_time = time.time()
    service_ready = False
    
    # Try to connect to the service health endpoint
    while not service_ready:
        # Check if we've exceeded maximum polling time
        if time.time() - start_time > MAX_POLLING_TIME:
            logger.warning("Timed out waiting for service to be ready")
            break
            
        try:
            response = requests.get(f"{GPU_SERVICE_URL}/health", timeout=5)
            
            if response.status_code == 200:
                logger.info("Service is ready")
                service_ready = True
            else:
                logger.info(f"Service not ready yet. Status code: {response.status_code}")
                time.sleep(10)
                
        except requests.exceptions.RequestException as e:
            logger.info(f"Service not ready yet: {str(e)}")
            time.sleep(10)
