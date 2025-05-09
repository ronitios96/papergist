// API endpoints
const API_BASE_URL = 'https://c6ydbiqqqe.execute-api.us-east-1.amazonaws.com/dev';
const SEARCH_ENDPOINT = `${API_BASE_URL}/search`;
const PAPER_ENDPOINT = `${API_BASE_URL}/paper`;
const SUMMARIZE_ENDPOINT = `${API_BASE_URL}/enqueue`;

// State management
let currentPage = 0;
let currentQuery = '';
let currentSortBy = 'relevance';
let hasNextPage = false;

// DOM Elements
const searchInput = document.getElementById('searchInput');
const searchButton = document.getElementById('searchButton');
const sortBySelect = document.getElementById('sortBy');
const resultsContainer = document.getElementById('resultsContainer');
const prevPageButton = document.getElementById('prevPage');
const nextPageButton = document.getElementById('nextPage');
const pageInfo = document.getElementById('pageInfo');
const summarySection = document.getElementById('summarySection');
const summaryContent = document.getElementById('summaryContent');
const loadingIndicator = document.getElementById('loadingIndicator');
const searchLoadingIndicator = document.getElementById('searchLoadingIndicator');
const errorModal = document.getElementById('errorModal');
const errorMessage = document.getElementById('errorMessage');
const closeModal = document.querySelector('.close');

// Event Listeners
searchButton.addEventListener('click', handleSearch);
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleSearch();
});
sortBySelect.addEventListener('change', handleSortChange);
prevPageButton.addEventListener('click', () => handlePageChange(-1));
nextPageButton.addEventListener('click', () => handlePageChange(1));
closeModal.addEventListener('click', () => errorModal.style.display = 'none');

// Search handler
async function handleSearch() {
    currentQuery = searchInput.value.trim();
    if (!currentQuery) {
        showError('Please enter a search query');
        return;
    }
    
    currentPage = 0;
    await fetchResults();
}

// Sort handler
async function handleSortChange() {
    currentSortBy = sortBySelect.value;
    currentPage = 0;
    await fetchResults();
}

// Page change handler
async function handlePageChange(delta) {
    currentPage += delta;
    await fetchResults();
}

// Fetch search results
async function fetchResults() {
    try {
        // Show loading indicator
        searchLoadingIndicator.style.display = 'flex';
        resultsContainer.innerHTML = '';
        
        // Hide summary section when starting new search
        summarySection.style.display = 'none';
        summaryContent.innerHTML = '';
        
        const response = await fetch(`${SEARCH_ENDPOINT}?query=${encodeURIComponent(currentQuery)}&page=${currentPage}&sort_by=${currentSortBy}`);
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        displayResults(data);
    } catch (error) {
        showError('Failed to fetch results. Please try again.');
    } finally {
        // Hide loading indicator
        searchLoadingIndicator.style.display = 'none';
    }
}

// Display search results
function displayResults(data) {
    show_pagination();
    resultsContainer.innerHTML = '';
    data.papers.forEach(paper => {
        const paperCard = createPaperCard(paper);
        resultsContainer.appendChild(paperCard);
    });
    
    // Update pagination
    hasNextPage = data.has_next_page;
    prevPageButton.disabled = currentPage === 0;
    nextPageButton.disabled = !hasNextPage;
    pageInfo.textContent = `Page ${currentPage + 1}`;
}

// pagination is hidden at the beginning
function show_pagination() {
  const e = document.querySelector('.pagination');
  e.style.display = 'flex';
}

// Create paper card
function createPaperCard(paper) {
    const card = document.createElement('div');
    card.className = 'paper-card';
    
    card.innerHTML = `
        <h3 class="paper-title">${paper.title}</h3>
        <p class="paper-authors">${paper.authors.join(', ')}</p>
        <p class="paper-summary">${paper.summary}</p>
        <button class="summarize-button" 
                data-arxiv-id="${paper.arxiv_id}"
                data-pdf-url="${paper.pdf_url}">Summarize</button>
    `;
    
    // Add click handler for summarize button
    card.querySelector('.summarize-button').addEventListener('click', () => {
        const button = card.querySelector('.summarize-button');
        const arxivId = button.getAttribute('data-arxiv-id');
        const pdfUrl = button.getAttribute('data-pdf-url');
        requestSummary(arxivId, pdfUrl);  // Pass both values
    });
    
    return card;
}

// Request paper summary
async function requestSummary(arxivId, pdfUrl) {
    try {
        // Show loading state
        summarySection.style.display = 'block';
        loadingIndicator.style.display = 'flex';
        summaryContent.innerHTML = '';
        
        const response = await fetch(`${SUMMARIZE_ENDPOINT}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                arxiv_id: arxivId,
                pdf_url: pdfUrl
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        // Start polling for summary
        pollForSummary(arxivId);
    } catch (error) {
        showError('Failed to request summary. Please try again.');
    }
}

// Poll for summary
async function pollForSummary(arxivId) {
    try {
        const response = await fetch(`${PAPER_ENDPOINT}/${arxivId}`);
        const data = await response.json();
        
        if (data.error) {
            showError(data.error);
            return;
        }
        
        if (data.processing) {
            // Still processing, poll again in 5 seconds
            setTimeout(() => pollForSummary(arxivId), 5000);
        } else if (data.summary) {
            // Summary is ready
            loadingIndicator.style.display = 'none';
            summaryContent.innerHTML = `
                <h3>${data.title}</h3>
                <p class="authors">${data.authors.join(', ')}</p>
                <div class="summary">${data.summary}</div>
            `;
        } else if (data.processing_error) {
            showError(data.processing_error);
        }
    } catch (error) {
        showError('Failed to fetch summary. Please try again.');
    }
}

// Show error modal
function showError(message) {
    errorMessage.textContent = message;
    errorModal.style.display = 'block';
}

// Close modal when clicking outside
window.addEventListener('click', (e) => {
    if (e.target === errorModal) {
        errorModal.style.display = 'none';
    }
});