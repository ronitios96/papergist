EC2 : 

Supports GPU 
Runs Ollama automatically
Has the relevant model based on the code

Boots up this combined-service.py on start 

Fetches batchsize set in global from SQS 
Processes it and updates the summary on Dynamo
Right now, also uploading on S3 just for testing (will remove this code)

Auto shuts down if the SQS is empty for more than 10 mins
