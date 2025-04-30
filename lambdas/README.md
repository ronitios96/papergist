Created three lambdas for now

First is for GET endpoint SEARCH using query and arXiv py framework.
Allows pagination, and other subtle features for a good frontend development. 

The second is for POST endpoint ENQUEUE, you need to provide it a complete arXiv object it will put it in dynamo and queue it SQS.
If item exists in DB, it will return that item from DB

The third is triggered by a EventScheduler running every 1 min and calling gpuhandler, which basically checks if queue is not empty, to boot up the GPU instance. 
