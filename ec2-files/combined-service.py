import os
import time
import json
import boto3
import logging
import requests
import threading
import subprocess
import hashlib
from io import BytesIO
from typing import List, Dict, Any
from datetime import datetime
from fastapi import FastAPI, Query
from pydantic import BaseModel

# Set up boto3 default session with region
boto3.setup_default_session(region_name="us-east-1")

# Configure logging
logger = logging.getLogger("combined-service")
logger.setLevel(logging.INFO)

# Console log handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(console_handler)

# Direct CloudWatch Logs integration
try:
    # Create a CloudWatch Logs client
    logs_client = boto3.client('logs', region_name='us-east-1')
    
    # Create log group if it doesn't exist
    try:
        logs_client.create_log_group(logGroupName='/ec2/combined-service')
    except logs_client.exceptions.ResourceAlreadyExistsException:
        pass
        
    # Create a log stream with timestamp
    log_stream_name = f"log-stream-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    logs_client.create_log_stream(
        logGroupName='/ec2/combined-service',
        logStreamName=log_stream_name
    )
    
    # Set up a custom logger for CloudWatch
    sequence_token = None
    
    def log_to_cloudwatch(message, level="INFO"):
        global sequence_token
        try:
            formatted_message = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{level}] {message}"
            
            kwargs = {
                'logGroupName': '/ec2/combined-service',
                'logStreamName': log_stream_name,
                'logEvents': [
                    {
                        'timestamp': int(datetime.now().timestamp() * 1000),
                        'message': formatted_message
                    }
                ]
            }
            
            if sequence_token:
                kwargs['sequenceToken'] = sequence_token
                
            response = logs_client.put_log_events(**kwargs)
            sequence_token = response.get('nextSequenceToken')
        except logs_client.exceptions.InvalidSequenceTokenException as e:
            # Get the correct sequence token
            sequence_token = e.response['Error']['Message'].split()[-1].strip("'")
            log_to_cloudwatch(message, level)  # Try again with correct token
        except Exception as e:
            print(f"Error logging to CloudWatch: {str(e)}")
    
    # Monkey patch the logger's info, error methods
    original_info = logger.info
    original_error = logger.error
    
    def info_with_cloudwatch(message, *args, **kwargs):
        original_info(message, *args, **kwargs)
        log_to_cloudwatch(message, "INFO")
    
    def error_with_cloudwatch(message, *args, **kwargs):
        original_error(message, *args, **kwargs)
        log_to_cloudwatch(message, "ERROR")
    
    logger.info = info_with_cloudwatch
    logger.error = error_with_cloudwatch
    
    cloudwatch_enabled = True
except Exception as e:
    print(f"Failed to set up CloudWatch logging: {str(e)}")
    # Fall back to console-only logging
    cloudwatch_enabled = False

logger.info("🚀 Combined service logger initialized" + (" with CloudWatch" if cloudwatch_enabled else ""))

from langchain_ollama import ChatOllama
from langchain_community.document_loaders.parsers.pdf import PyMuPDFParser
from langchain_core.document_loaders.blob_loaders import Blob
from langchain_core.documents import Document

if os.environ.get("DEV_MODE", "False").lower() == "true":
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ["MPS_NO_ACCELERATOR"] = "1"

SQS_QUEUE_URL = os.environ.get('SQS_QUEUE_URL', 'https://sqs.us-east-1.amazonaws.com/071214564206/gpu-task-queue')
COOLDOWN_MINUTES = int(os.environ.get('COOLDOWN_MINUTES', '10'))
MAX_IDLE_TIME = int(os.environ.get('MAX_IDLE_TIME', '30'))
MAX_BATCH_SIZE = int(os.environ.get('MAX_BATCH_SIZE', '5'))
DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE', 'PaperSummaries')

app = FastAPI()
task_processor = None

logger.info("🚀 Starting Combined PDF Summarizer and Task Processor Service")

class BytesIOPyMuPDFLoader:
    def __init__(self, pdf_stream: BytesIO, *, extract_images: bool = False, **kwargs) -> None:
        self.pdf_stream = pdf_stream
        self.extract_images = extract_images
        self.text_kwargs = kwargs

    def load(self, **kwargs) -> List[Document]:
        blob = Blob.from_data(self.pdf_stream.getvalue(), path="stream")
        parser = PyMuPDFParser(text_kwargs=self.text_kwargs, extract_images=self.extract_images)
        return parser.parse(blob)

def download_pdf(url: str) -> bytes:
    logger.info(f"📥 Downloading PDF from: {url}")
    start_time = time.time()
    response = requests.get(url)
    if response.status_code != 200:
        logger.error(f"❌ Failed to download PDF: {url}")
        raise RuntimeError(f"Failed to download PDF: {url}")
    logger.info(f"✅ PDF downloaded in {time.time() - start_time:.2f}s, size: {len(response.content)} bytes")
    return response.content

def extract_entire_text(pdf_bytes: bytes) -> str:
    logger.info("🔍 Extracting text from PDF")
    start_time = time.time()
    loader = BytesIOPyMuPDFLoader(BytesIO(pdf_bytes))
    pages = loader.load()
    text = "\n\n".join(page.page_content for page in pages)
    logger.info(f"✅ Text extracted in {time.time() - start_time:.2f}s, extracted {len(text)} characters")
    return text

def generate_hash_string(text: str, char_limit: int = 100) -> str:
    """Generate a hash string from the first N characters of the text."""
    # Take first char_limit characters, remove spaces, newlines, and make lowercase
    if len(text) < char_limit:
        char_limit = len(text)
    
    # Remove both spaces and newline characters, then convert to lowercase
    clean_text = text[:char_limit].replace(" ", "").replace("\n", "").replace("\r", "").lower()
    logger.info(f"🔑 Generated hash string from first {char_limit} characters")
    return clean_text

def summarize_whole_text(text: str) -> str:
    logger.info("🤖 Summarizing with Ollama")
    start_time = time.time()

    llm = ChatOllama(
        model="llama3.2:latest",
        temperature=0
    )

    prompt = f"""
You are a research assistant. Read the following research paper and write a detailed, comprehensive, and technical summary.
Preserve important terminology, methods, and findings. Be as exhaustive and accurate as possible.

--- START OF PAPER ---
{text}
--- END OF PAPER ---
"""
    result = llm.invoke(prompt)
    summary = result.content if hasattr(result, "content") else str(result)
    logger.info(f"✅ Summarization completed in {time.time() - start_time:.2f}s, summary length: {len(summary)} chars")
    return summary

@app.get("/summarize")
def summarize(pdf_url: str = Query(..., description="URL of the PDF")):
    logger.info(f"📋 Received summarization request for: {pdf_url}")
    try:
        pdf_bytes = download_pdf(pdf_url)
        full_text = extract_entire_text(pdf_bytes)
        summary = summarize_whole_text(full_text)
        return {"summary": summary.strip()}
    except Exception as e:
        logger.error(f"❌ Error processing request: {str(e)}")
        return {"error": str(e)}, 500

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "model": "combined-pdf-summarizer",
        "batch_processor": "running" if task_processor is not None else "not_running",
        "cloudwatch_logging": "enabled" if cloudwatch_enabled else "disabled"
    }

@app.get("/queue/status")
def queue_status():
    if task_processor is None:
        return {"error": "Task processor not running"}

    try:
        response = task_processor.sqs.get_queue_attributes(
            QueueUrl=SQS_QUEUE_URL,
            AttributeNames=['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible']
        )
        return {
            "visible_messages": int(response['Attributes']['ApproximateNumberOfMessages']),
            "in_flight_messages": int(response['Attributes']['ApproximateNumberOfMessagesNotVisible']),
            "local_queue_size": len(task_processor.task_queue),
            "is_processing": task_processor.is_processing,
            "cooldown_active": task_processor.cooldown_timer is not None and task_processor.cooldown_timer.is_alive(),
            "last_activity": task_processor.last_activity_time.isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

class GPUTaskProcessor:
    def __init__(self):
        self.sqs = boto3.client('sqs', region_name='us-east-1')
        self.dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        self.table = self.dynamodb.Table(DYNAMODB_TABLE)
        self.task_queue = []
        self.is_processing = False
        self.last_activity_time = datetime.now()
        self.cooldown_timer = None
        self.shutdown_requested = False

        self.shutdown_monitor = threading.Thread(target=self._monitor_idle_time)
        self.shutdown_monitor.daemon = True
        self.shutdown_monitor.start()

        self.processing_thread = threading.Thread(target=self._processing_loop)
        self.processing_thread.daemon = True
        self.processing_thread.start()

    def _monitor_idle_time(self):
        while not self.shutdown_requested:
            idle_minutes = (datetime.now() - self.last_activity_time).total_seconds() / 60
            if idle_minutes > MAX_IDLE_TIME:
                logger.info(f"Maximum idle time ({MAX_IDLE_TIME} minutes) reached. Initiating shutdown.")
                self._shutdown_instance()
                break
            time.sleep(60)

    def _shutdown_instance(self):
        logger.info("🛑 Shutting down instance...")
        self.shutdown_requested = True
        try:
            subprocess.run(['sudo', 'shutdown', '-h', 'now'])
        except Exception as shutdown_error:
            logger.error(f"❌ Error using system shutdown: {str(shutdown_error)}")

    def _reset_cooldown_timer(self):
        if self.cooldown_timer is not None:
            self.cooldown_timer.cancel()

        self.cooldown_timer = threading.Timer(
            COOLDOWN_MINUTES * 60,
            self._shutdown_instance
        )
        self.cooldown_timer.daemon = True
        self.cooldown_timer.start()
        logger.info(f"⏲️ Cooldown timer set for {COOLDOWN_MINUTES} minutes")

    def _processing_loop(self):
        logger.info("🔄 Task processing loop started")
        while not self.shutdown_requested:
            has_messages = self.fetch_tasks()
            if not has_messages:
                time.sleep(20)
        logger.info("🛑 Task processing loop stopped")

    def fetch_tasks(self):
        try:
            response = self.sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=MAX_BATCH_SIZE,
                VisibilityTimeout=600,
                WaitTimeSeconds=10
            )

            messages = response.get('Messages', [])
            if messages:
                logger.info(f"📥 Received {len(messages)} messages from SQS")
                self.last_activity_time = datetime.now()

                tasks = []
                for message in messages:
                    try:
                        body = json.loads(message.get('Body', '{}'))
                        tasks.append({
                            'arxiv_id': body.get('arxiv_id'),
                            'pdf_url': body.get('pdf_url'),
                            'task_id': body.get('task_id'),
                            'receipt_handle': message.get('ReceiptHandle'),
                            'timestamp': body.get('timestamp')
                        })
                    except json.JSONDecodeError:
                        logger.error(f"❌ Invalid JSON in message: {message.get('Body')}")

                self.add_tasks(tasks)
            else:
                logger.info("📭 No messages in queue")

            return len(messages) > 0

        except Exception as e:
            logger.error(f"❌ Error fetching messages from SQS: {str(e)}")
            return False

    def add_tasks(self, tasks: List[Dict[str, Any]]):
        self.task_queue.extend(tasks)
        logger.info(f"📋 Added {len(tasks)} tasks to queue. Queue size: {len(self.task_queue)}")

        if not self.is_processing:
            self.process_queue()

    def process_queue(self):
        if self.shutdown_requested:
            logger.info("🛑 Shutdown requested, not processing queue")
            return

        self.is_processing = True
        while self.task_queue and not self.shutdown_requested:
            task = self.task_queue.pop(0)
            try:
                logger.info(f"⚙️ Processing task {task.get('task_id')}")
                self.process_single_task(task)
            except Exception as e:
                logger.error(f"❌ Error processing task {task.get('task_id')}: {str(e)}")
            self.last_activity_time = datetime.now()

        self.is_processing = False
        if not self.shutdown_requested:
            self._reset_cooldown_timer()

    def process_single_task(self, task: Dict[str, Any]):
        """Process a single PDF summarization task and save result to DynamoDB"""
        pdf_url = task.get('pdf_url')
        task_id = task.get('task_id', datetime.now().strftime('%Y%m%d%H%M%S'))
        arxiv_id = task.get('arxiv_id')

        if not pdf_url:
            logger.error("❌ Missing PDF URL in task")
            self._delete_message(task.get('receipt_handle'))
            return

        if not arxiv_id:
            logger.error("❌ Missing arXiv ID in task")
            self._delete_message(task.get('receipt_handle'))
            return

        try:
            # First update the DynamoDB item to mark it as processing
            try:
                self.table.update_item(
                    Key={'arxiv_id': arxiv_id},
                    UpdateExpression="SET processing = :proc",
                    ExpressionAttributeValues={':proc': True}
                )
                logger.info(f"🔄 Updated DynamoDB: marked arxiv_id {arxiv_id} as processing")
            except Exception as dynamo_error:
                logger.error(f"❌ Error updating DynamoDB (processing start): {str(dynamo_error)}")

            # Process PDF as before
            pdf_bytes = download_pdf(pdf_url)
            full_text = extract_entire_text(pdf_bytes)
            
            # Generate hash_string from first 100 characters
            hash_string = generate_hash_string(full_text, 100)
            logger.info(f"🔑 Generated hash string for arxiv_id {arxiv_id}")
            
            # Update DynamoDB with hash_string
            try:
                self.table.update_item(
                    Key={'arxiv_id': arxiv_id},
                    UpdateExpression="SET hash_string = :hash",
                    ExpressionAttributeValues={':hash': hash_string}
                )
                logger.info(f"📝 Updated DynamoDB: added hash_string for arxiv_id {arxiv_id}")
            except Exception as dynamo_error:
                logger.error(f"❌ Error updating DynamoDB (hash_string): {str(dynamo_error)}")
            
            # Now run summarization
            summary = summarize_whole_text(full_text)
            logger.info(f"✅ Successfully summarized PDF for arxiv_id {arxiv_id}")

            # Update DynamoDB with the summary
            try:
                self.table.update_item(
                    Key={'arxiv_id': arxiv_id},
                    UpdateExpression="SET summary = :sum, processing = :proc",
                    ExpressionAttributeValues={
                        ':sum': summary,
                        ':proc': False
                    }
                )
                logger.info(f"📤 Updated DynamoDB: added summary for arxiv_id {arxiv_id} and marked as not processing")
            except Exception as dynamo_error:
                logger.error(f"❌ Error updating DynamoDB (summary): {str(dynamo_error)}")
                # Try to update just the processing flag
                try:
                    self.table.update_item(
                        Key={'arxiv_id': arxiv_id},
                        UpdateExpression="SET processing = :proc, processing_error = :err",
                        ExpressionAttributeValues={
                            ':proc': False,
                            ':err': f"Error updating summary: {str(dynamo_error)}"
                        }
                    )
                except Exception as recovery_error:
                    logger.error(f"❌ Error during recovery update to DynamoDB: {str(recovery_error)}")

            # For backwards compatibility, still save to S3 as well
            try:
                s3 = boto3.client('s3', region_name='us-east-1')
                filename = pdf_url.split('/')[-1].split('.')[0] or "document"
                timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                s3_key = f"summaries/{filename}_{task_id}_{timestamp}.txt"

                s3.put_object(
                    Bucket='gpu-testing-bucket',
                    Key=s3_key,
                    Body=summary.encode('utf-8'),
                    ContentType='text/plain',
                    Metadata={
                        'source_url': pdf_url,
                        'task_id': task_id,
                        'arxiv_id': arxiv_id,
                        'timestamp': timestamp,
                        'summary_length': str(len(summary))
                    }
                )
                logger.info(f"📤 Uploaded summary to S3: s3://gpu-testing-bucket/{s3_key}")
            except Exception as s3_error:
                logger.error(f"❌ Error uploading to S3: {str(s3_error)}")

            self._delete_message(task.get('receipt_handle'))

        except Exception as e:
            logger.error(f"❌ Error processing PDF: {str(e)}")
            # Update DynamoDB to mark processing as done with error
            try:
                self.table.update_item(
                    Key={'arxiv_id': arxiv_id},
                    UpdateExpression="SET processing = :proc, processing_error = :err",
                    ExpressionAttributeValues={
                        ':proc': False,
                        ':err': str(e)
                    }
                )
                logger.info(f"⚠️ Updated DynamoDB: marked arxiv_id {arxiv_id} as not processing with error")
            except Exception as dynamo_error:
                logger.error(f"❌ Error updating DynamoDB with error state: {str(dynamo_error)}")

    def _delete_message(self, receipt_handle: str):
        if not receipt_handle:
            return
        try:
            self.sqs.delete_message(
                QueueUrl=SQS_QUEUE_URL,
                ReceiptHandle=receipt_handle
            )
            logger.info("🗑️ Message deleted from queue")
        except Exception as e:
            logger.error(f"❌ Error deleting message from SQS: {str(e)}")

@app.on_event("startup")
def startup_event():
    global task_processor
    logger.info("🚀 Initializing GPU Task Processor")
    task_processor = GPUTaskProcessor()

@app.on_event("shutdown")
def app_shutdown():
    logger.info("Application shutting down...")
    if task_processor:
        task_processor.shutdown_requested = True

@app.get("/debug/test-shutdown")
def test_shutdown():
    logger.info("🧪 Manual shutdown test initiated")
    if task_processor:
        logger.info("SIMULATION: Would shut down instance now if this wasn't a test")
        task_processor._reset_cooldown_timer()
        logger.info("✅ Cooldown timer has been reset for testing")
        return {
            "status": "shutdown_simulated",
            "cooldown_minutes": COOLDOWN_MINUTES,
            "cooldown_timer_active": task_processor.cooldown_timer is not None,
            "note": "Real shutdown not triggered, check logs for simulation details"
        }
    else:
        return {"error": "Task processor not running"}

if __name__ == "__main__":
    import uvicorn
    logger.info("🌐 Starting server on http://0.0.0.0:8082")
    uvicorn.run(app, host="0.0.0.0", port=8082)