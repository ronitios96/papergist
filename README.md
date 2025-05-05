# papergist
Cloud Final Project

071214564206 : AWS Account Id  
AdminUser : AWS IAM (Read Only Access for now)
SecurePassword123! : AWS Password

EC2 SSH KEY : Let me know if you need it, I'll provide. You can observe Cloudwatch logs for EC2 behaviour for now.

Search Endpoint : https://c6ydbiqqqe.execute-api.us-east-1.amazonaws.com/dev/search?query=machine+learning 
^Pick one json from this 

Enqueue Endpoint : 
curl -X POST "https://c6ydbiqqqe.execute-api.us-east-1.amazonaws.com/dev/enqueue" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Lecture Notes: Optimization for Machine Learning",
    "authors": ["Elad Hazan"],
    "summary": "Lecture notes on optimization for machine learning, derived from a course at\nPrinceton University and tutorials given in MLSS, Buenos Aires, as well as\nSimons Foundation, Berkeley.",
    "published": "2019-09-08T21:49:42+00:00",
    "updated": "2019-09-08T21:49:42+00:00",
    "pdf_url": "http://arxiv.org/pdf/1909.03550v1",
    "arxiv_id": "1909.03550v1",
    "primary_category": "cs.LG",
    "categories": ["cs.LG","stat.ML"]
  }'

After this, you can observe the summary in S3 bucket and also in Dynamo Table
link to diagram : https://lucid.app/lucidchart/25c26bdc-cafc-4d97-8e94-f57ed704905e/edit?viewport_loc=-881%2C-404%2C3088%2C1743%2C0_0&invitationId=inv_19800162-b825-4b73-89db-ed74cee52c53  


<img width="608" alt="image" src="https://github.com/user-attachments/assets/41611a56-e84e-4b18-b7c9-5816aa92a6ce" />

# Cost Motivation in terms of scaling 

# Cost Comparison: Processing 1,000 Academic Papers Over One Month

| Factor | GPU EC2 (On/Off) | LLM APIs | Amazon Bedrock |
|--------|-----------------|----------|---------------|
| **Average Paper Size** | ~10,000 tokens per research paper (15 pages) | ~10,000 tokens per research paper (15 pages) | ~10,000 tokens per research paper (15 pages) |
| **Total Input Tokens** | 10M tokens | 10M tokens | 10M tokens |
| **Output Tokens** | Not applicable | ~1M tokens (summary/analysis) | ~1M tokens (summary/analysis) |
| **Hardware/Model** | g4dn.xlarge ($0.526/hour) | OpenAI GPT-4 or Claude | Amazon Titan or Claude models |
| **Hourly Cost** | $0.526/hour for g4dn.xlarge | N/A (token-based) | N/A (on-demand) or $1-4/hour (provisioned) |
| **Processing Time** | ~500 hours (estimate) | N/A | N/A |
| **Token Pricing** | N/A | $0.01-0.03/1K input tokens<br>$0.03-0.06/1K output tokens | $0.001-0.01/1K input tokens<br>$0.003-0.03/1K output tokens |
| **Monthly Fixed Costs** | Storage: ~$30-50 | None | None |
| **Total Cost Estimate** | $263-$400 | $100,000-$300,000 | $10,000-$30,000 |
| **Cost per Paper** | $0.26-$0.40 | $100-$300 | $10-$30 |
