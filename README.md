# papergist
Cloud Final Project

071214564206 : AWS Account Id  
ReadOnlyUser : AWS IAM (Read Only Access for now)
SecurePassword123! : AWS Password

EC2 SSH KEY : Let me know if you need it, I'll provide. You can observe Cloudwatch logs for EC2 behaviour for now.

Search Endpoint : https://c6ydbiqqqe.execute-api.us-east-1.amazonaws.com/dev/search?query=machine+learning 
^Pick one json from this 

Run a curl like this to post request: 
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

<img width="608" alt="image" src="https://github.com/user-attachments/assets/41611a56-e84e-4b18-b7c9-5816aa92a6ce" />

