import os
import json
import logging
from typing import Optional, List, Dict, Any
import arxiv

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def convert_paper_to_dict(paper):
    """Convert a paper from arxiv library to a dictionary"""
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


def search_papers(
    query: str, page: int = 0, page_size: int = 10, sort_by: str = "relevance"
):
    """Search for papers using the arXiv API"""
    logger.info(
        f"📋 Received search request: query='{query}', page={page}, page_size={page_size}, sort_by={sort_by}"
    )

    # Map sort criteria to arxiv.SortCriterion
    sort_criterion = arxiv.SortCriterion.Relevance
    if sort_by == "submitted_date":
        sort_criterion = arxiv.SortCriterion.SubmittedDate
    elif sort_by == "last_updated":
        sort_criterion = arxiv.SortCriterion.LastUpdatedDate

    # Calculate start index for pagination
    start = page * page_size

    # Create client and search
    client = arxiv.Client()

    # Create search query without start parameter
    search = arxiv.Search(
        query=query,
        max_results=page_size + 1,  # Get one extra to check if there's a next page
        sort_by=sort_criterion,
    )

    try:
        # Use the client's parameters to handle pagination
        results = list(client.results(search, offset=start))

        # Check if there's a next page
        has_next_page = len(results) > page_size

        # Trim to requested page size
        if has_next_page:
            results = results[:page_size]

        # Convert to response format
        papers = [convert_paper_to_dict(paper) for paper in results]

        logger.info(f"✅ Found {len(papers)} papers for query '{query}'")

        return {
            "papers": papers,
            "total_results": len(papers)
            + (
                page * page_size
            ),  # Approximation since arXiv API doesn't provide total count
            "page": page,
            "page_size": page_size,
            "has_next_page": has_next_page,
        }

    except Exception as e:
        logger.error(f"❌ Error processing search: {str(e)}")
        return {"error": str(e)}


def get_paper(paper_id: str):
    """Get a single paper by its arXiv ID"""
    logger.info(f"📋 Received paper request: id='{paper_id}'")

    client = arxiv.Client()
    search = arxiv.Search(id_list=[paper_id])

    try:
        paper = next(client.results(search))
        response = convert_paper_to_dict(paper)

        logger.info(f"✅ Retrieved paper '{paper_id}'")
        return response

    except StopIteration:
        logger.error(f"❌ Paper '{paper_id}' not found")
        return {"error": "Paper not found"}

    except Exception as e:
        logger.error(f"❌ Error retrieving paper '{paper_id}': {str(e)}")
        return {"error": str(e)}


def lambda_handler(event, context):
    """AWS Lambda handler function"""
    logger.info(f"Received event: {json.dumps(event)}")
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
    }
    # Determine the path and HTTP method
    path = event.get("path", "")
    http_method = event.get("httpMethod", "GET")

    # Get query parameters
    query_params = event.get("queryStringParameters", {}) or {}

    # Handle health check
    if path == "/health":
        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": json.dumps({"status": "healthy", "service": "arxiv-search-lambda"}),
        }

    # Handle search
    elif path == "/search" and http_method == "GET":
        query = query_params.get("query", "")
        page = int(query_params.get("page", 0))
        page_size = int(query_params.get("page_size", 10))
        sort_by = query_params.get("sort_by", "relevance")

        result = search_papers(query, page, page_size, sort_by)

        # Check if there was an error
        if "error" in result:
            return {
                "statusCode": 500,
                "headers": cors_headers,
                "body": json.dumps(result),
            }

        return {"statusCode": 200, "headers": cors_headers, "body": json.dumps(result)}

    # Handle paper retrieval
    elif path.startswith("/paper/") and http_method == "GET":
        # Extract paper ID from path
        paper_id = path.split("/paper/")[1]

        result = get_paper(paper_id)

        # Check if there was an error
        if "error" in result and result["error"] == "Paper not found":
            return {
                "statusCode": 404,
                "headers": cors_headers,
                "body": json.dumps(result),
            }
        elif "error" in result:
            return {
                "statusCode": 500,
                "headers": cors_headers,
                "body": json.dumps(result),
            }

        return {"statusCode": 200, "headers": cors_headers, "body": json.dumps(result)}

    # Handle unknown routes
    else:
        return {
            "statusCode": 404,
            "headers": cors_headers,
            "body": json.dumps({"error": f"Route not found: {path}"}),
        }


# This allows the code to still be run locally using uvicorn
# but it's not needed for Lambda deployment
if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI, Query

    app = FastAPI()

    @app.get("/search")
    def api_search_papers(
        query: str = Query(..., description="Search query"),
        page: int = Query(0, description="Page number (0-based)"),
        page_size: int = Query(10, description="Results per page"),
        sort_by: str = Query(
            "relevance",
            description="Sort criterion: relevance, submitted_date, or last_updated",
        ),
    ):
        return search_papers(query, page, page_size, sort_by)

    @app.get("/paper/{paper_id}")
    def api_get_paper(paper_id: str):
        return get_paper(paper_id)

    @app.get("/health")
    def health_check():
        return {"status": "healthy", "service": "arxiv-search-service"}

    logger.info("🌐 Starting arXiv search service on http://0.0.0.0:8083")
    uvicorn.run(app, host="0.0.0.0", port=8083)
