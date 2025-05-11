🧠 Paper Gist: AI Research Paper Summarization Tool
Paper Gist is a cost-efficient cloud-native platform to summarize long AI research papers using a GPU-hosted LLM—without incurring the high costs of commercial APIs like OpenAI or AWS Bedrock. It caches and reuses summaries to optimize both latency and expense.


🔍 Problem Statement
Summarizing large academic PDFs through commercial LLM APIs becomes prohibitively expensive at scale. Each request processes entire documents, resulting in high inference costs even for repeated or duplicate uploads.

✅ Key Features
arXiv Search + Summarize: Users can search papers from arXiv and queue them for summarization.

Manual Uploads: PDF/DOCX uploads supported; we check for existing cached summaries using hash-based matching.

GPU-Efficient Queue Execution: A scheduled queue triggers an EC2 G5 GPU instance only when needed, shutting it down automatically if idle.

Caching Layer: Summaries are cached using DynamoDB (by arxiv_id or document hash) to avoid repeated summarization.

Frontend: Lightweight HTML, CSS, and JS-based interface. Users can track their uploads via browser-local cache under “My Uploads”.

🧱 Architecture Overview
Component	Description
Frontend	HTML/CSS/JS app for users to search, upload, and view summaries.
Amazon API Gateway	Public HTTP interface to backend Lambda APIs (/search, /enqueue).
Lambda Functions	Stateless compute for: checking database (search) and queuing new summarization tasks (enqueue).
Amazon DynamoDB	Stores summaries with two indexes:
• Primary Index: arxiv_id
• GSI: hash_string for manual uploads
S3 Bucket	Hosts user-uploaded PDFs and generates URLs for summarization.
SQS Queue	Buffers summarization tasks before GPU processing.
EventBridge	Triggers a Lambda every minute to check if GPU should start.
EC2 G5 Instance	Runs combined-service.py which processes tasks using llama3.2:latest model.
LLM	A hosted, optimized LLaMA-3.2 model for low-latency summarization.

🚀 How It Works
User searches arXiv or uploads a file from frontend.

API Gateway routes the request to a Lambda:

Checks DynamoDB for cached summary

If not found, queues the task

EventBridge runs every 1 min to check the queue.

If queue has tasks:

Starts EC2 GPU instance

combined-service.py dequeues and summarizes

Result is cached back into DynamoDB

EC2 shuts itself down once queue is empty, saving costs.

💡 Cost Optimization Strategy
Avoids repeated summarization through strong caching.

EC2 lifecycle controlled dynamically using queue length.

No always-on LLM API billing — summarization only happens on demand.

🔧 Technologies Used
AWS EC2 (G5), Lambda, SQS, DynamoDB, S3, EventBridge

Amazon API Gateway

HTML/CSS/JavaScript (Frontend)

Python (Backend)

HuggingFace Transformers (llama3.2:latest)

🛠 Possible Improvements
🔐 Add authentication and session-based user tracking.

⚡ Provide instant summarization APIs for premium users.

🧠 Host stronger/faster LLM models as compute budget scales.

🧾 Persist user history across devices (currently browser-local only).

🔎 Add semantic search over summaries (Typesense/OpenSearch).

📈 Highlight trending or most-requested papers to avoid repeated inference.

📦 Local Setup (Coming Soon)
We'll provide Docker + Terraform scripts to simulate local development + deploy on AWS.

