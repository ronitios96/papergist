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
GPU_INSTANCE_ID = os.environ.get('GPU_INSTANCE_ID', 'i-0e9d9c51f67dfad3a')
# Maximum polling time in seconds
MAX_POLLING_TIME = 300

def lambda_handler(event, context):
    logger.info("Processing SQS event trigger")
    
    try:
        # Check number of messages in the queue
        queue_attributes = sqs.get_queue_attributes(
            QueueUrl=SQS_QUEUE_URL,
            AttributeNames=['ApproximateNumberOfMessages']
        )
        message_count = int(queue_attributes['Attributes']['ApproximateNumberOfMessages'])
        logger.info(f"Approximate number of messages in queue: {message_count}")
        
        if message_count == 0:
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'No messages in queue'})
            }

        if not GPU_INSTANCE_ID:
            logger.error("GPU_INSTANCE_ID environment variable not set")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'GPU_INSTANCE_ID environment variable not set'})
            }

        instance_state = get_instance_state(GPU_INSTANCE_ID)
        logger.info(f"Current GPU instance state: {instance_state}")

        if instance_state in ['stopped', 'stopping']:
            logger.info(f"Starting GPU instance {GPU_INSTANCE_ID}")
            ec2.start_instances(InstanceIds=[GPU_INSTANCE_ID])
            wait_for_instance_to_run(GPU_INSTANCE_ID)
            logger.info("Skipping health check — assuming service is running after EC2 boots")

        elif instance_state == 'running':
            logger.info("Instance is already running — skipping health check")

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
            'body': json.dumps({'error': str(e)})
        }

def get_instance_state(instance_id):
    response = ec2.describe_instances(InstanceIds=[instance_id])
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            return instance['State']['Name']
    return 'unknown'

def wait_for_instance_to_run(instance_id):
    logger.info("Waiting for instance to be in running state")
    start_time = time.time()
    current_state = get_instance_state(instance_id)

    while current_state != 'running':
        if time.time() - start_time > MAX_POLLING_TIME:
            logger.warning(f"Timed out waiting for instance to start. Current state: {current_state}")
            break

        logger.info(f"Instance state: {current_state}, waiting...")
        time.sleep(10)
        current_state = get_instance_state(instance_id)
