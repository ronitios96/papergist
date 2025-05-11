import os
import json
import logging
from typing import Optional, List, Dict, Any
import arxiv
import boto3
from boto3.dynamodb.conditions import Key

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
TABLE_NAME = os.environ.get("DYNAMO_TABLE_NAME", "PaperSummaries")
table = dynamodb.Table(TABLE_NAME)

def get_dynamo_summary(arxiv_id: str) -> Optional[Dict[str, Any]]:
    try:
        response = table.get_item(Key={"arxiv_id": arxiv_id})
        if "Item" in response:
            return response["Item"]
        return None
    except Exception as e:
        logger.error(f"Error getting summary from DynamoDB: {str(e)}")
        return None

def convert_paper_to_dict(paper):
    return {
        "title": paper.title,
        "authors": [author.name for author in paper.authors],
        "summary": paper.summary,
        "published": paper.published.isoformat() if paper.published else None,
        "updated": paper.updated.isoformat() if paper.updated else None,
        "pdf_url": paper.pdf_url,
        "arxiv_id": paper.get_short_id(),
        "primary_category": paper.primary_category,
        "categories": paper.categories,
    }

def search_papers(query: str, page: int = 0, page_size: int = 10, sort_by: str = "relevance"):
    logger.info(f"📋 Received search request: query='{query}', page={page}, page_size={page_size}, sort_by={sort_by}")
    sort_criterion = arxiv.SortCriterion.Relevance
    if sort_by == "submitted_date":
        sort_criterion = arxiv.SortCriterion.SubmittedDate
    elif sort_by == "last_updated":
        sort_criterion = arxiv.SortCriterion.LastUpdatedDate

    start = page * page_size
    client = arxiv.Client()
    search = arxiv.Search(query=query, max_results=page_size + 1, sort_by=sort_criterion)

    try:
        results = list(client.results(search, offset=start))
        has_next_page = len(results) > page_size
        if has_next_page:
            results = results[:page_size]
        papers = [convert_paper_to_dict(paper) for paper in results]
        logger.info(f"✅ Found {len(papers)} papers for query '{query}'")
        return {
            "papers": papers,
            "total_results": len(papers) + (page * page_size),
            "page": page,
            "page_size": page_size,
            "has_next_page": has_next_page,
        }
    except Exception as e:
        logger.error(f"❌ Error processing search: {str(e)}")
        return {"error": str(e)}

def get_paper(paper_id: str):
    logger.info(f"📋 Received paper request: id='{paper_id}'")
    dynamo_data = get_dynamo_summary(paper_id)
    if dynamo_data:
        if not dynamo_data.get("processing", False) and dynamo_data.get("summary", ""):
            logger.info(f"Found completed paper '{paper_id}' with summary in DynamoDB")
            return dynamo_data
        elif dynamo_data.get("processing", False):
            task_id = dynamo_data.get("task_id", "unknown")
            logger.info(f"Paper '{paper_id}' is still being processed (task_id: {task_id})")
            return {
                "message": f"Task id {task_id} is under process right now",
                "processing": True,
                "arxiv_id": paper_id
            }
    logger.info(f"No data found for paper '{paper_id}'")
    return {
        "message": f"No data found for paper ID {paper_id}",
        "arxiv_id": paper_id
    }

def lambda_handler(event, context):
    logger.info(f"Received event: {json.dumps(event)}")
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

    path = event.get("path", "")
    http_method = event.get("httpMethod", "GET")
    query_params = event.get("queryStringParameters", {}) or {}

    if path == "/health":
        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps({"status": "healthy", "service": "arxiv-search-lambda"}),
        }

    elif path == "/search" and http_method == "GET":
        query = query_params.get("query", "")
        page = int(query_params.get("page", 0))
        page_size = int(query_params.get("page_size", 10))
        sort_by = query_params.get("sort_by", "relevance")
        result = search_papers(query, page, page_size, sort_by)
        if "error" in result:
            return {"statusCode": 500, "headers": cors_headers, "body": json.dumps(result)}
        return {"statusCode": 200, "headers": cors_headers, "body": json.dumps(result)}

    elif path.startswith("/paper/") and not path.startswith("/paper/hash") and http_method == "GET":
        paper_id = path.split("/paper/")[1]
        result = get_paper(paper_id)
        if "message" in result and "No data found" in result.get("message", ""):
            return {"statusCode": 404, "headers": cors_headers, "body": json.dumps(result)}
        return {"statusCode": 200, "headers": cors_headers, "body": json.dumps(result)}

    elif path == "/paper/hash" and http_method == "POST":
        try:
            body = json.loads(event.get("body", "{}"))
            hash_id = body.get("hashId", "")
            if not hash_id:
                return {
                    "statusCode": 400,
                    "headers": cors_headers,
                    "body": json.dumps({"error": "Missing 'hashId' in request body"})
                }

            response = table.query(
                IndexName="hash-string-index",
                KeyConditionExpression=Key("hash_string").eq(hash_id)
            )
            items = response.get("Items", [])
            if not items:
                return {
                    "statusCode": 404,
                    "headers": cors_headers,
                    "body": json.dumps({"message": f"No paper found for hash ID {hash_id}"})
                }

            item = items[0]

            return {
                "statusCode": 200,
                "headers": cors_headers,
                "body": json.dumps(item)
            }

        except Exception as e:
            error_message = str(e)
            logger.error(f"❌ Error querying hash_string-index (POST): {error_message}")
            return {
                "statusCode": 500,
                "headers": cors_headers,
                "body": json.dumps({"error": f"Failed to fetch by hash ID: {error_message}"})
            }

    else:
        return {
            "statusCode": 404,
            "headers": cors_headers,
            "body": json.dumps({"error": f"Route not found: {path}"}),
        }
