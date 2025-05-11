// API endpoints
const API_BASE_URL = 'https://6wl5b8js92.execute-api.us-east-1.amazonaws.com/dev';
const SEARCH_ENDPOINT = `${API_BASE_URL}/search`;
const PAPER_ENDPOINT = `${API_BASE_URL}/paper`;
const SUMMARIZE_ENDPOINT = `${API_BASE_URL}/enqueue`;
const HASH_CHECK_ENDPOINT = `${API_BASE_URL}/paper/hash`;

// State management
let currentPage = 0;
let currentQuery = '';
let currentSortBy = 'relevance';
let hasNextPage = false;
let currentView = 'search'; // 'search' or 'paper' or 'uploads'
let currentPaperData = null; // Store the current paper data for file:// protocol
let myUploads = []; // Store the list of user uploads
let isApiCallInProgress = false; // Track if any API call is in progress

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
const searchSection = document.querySelector('.search-section');
const resultsSection = document.querySelector('.results-section');
const paperView = document.getElementById('paperView');
const paperContent = document.getElementById('paperContent');
const returnToSearchBtn = document.getElementById('returnToSearch');
const toastContainer = document.getElementById('toastContainer');

// Utility function to set API call state
function setApiCallState(inProgress) {
    isApiCallInProgress = inProgress;
    
    // Disable/enable all UI interactions based on API call state
    if (inProgress) {
        disableAllUIInteractions();
    } else {
        enableAllUIInteractions();
    }
}

// Function to generate a UUID
function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

// Function to save uploads to localStorage
function saveUploadsToStorage() {
    localStorage.setItem('papergist-uploads', JSON.stringify(myUploads));
}

// Function to load uploads from localStorage
function loadUploadsFromStorage() {
    const storedUploads = localStorage.getItem('papergist-uploads');
    if (storedUploads) {
        myUploads = JSON.parse(storedUploads);
    }
}

// Function to add a new upload to localStorage
function addUploadToStorage(uploadData) {
    myUploads.push(uploadData);
    saveUploadsToStorage();
}

// Function to check if a paper hash exists in the database
async function checkPaperHashExists(hash) {
    // We don't set API call state here because it's called from uploadFile
    // which already manages the UI state
    
    try {
        const response = await fetch(HASH_CHECK_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ hashId: hash })
        });
        
        if (!response.ok) {
            // If response is not ok (e.g., 404, 500), assume no match
            return null;
        }
        
        const data = await response.json();
        console.log("Hash check response:", data);
        
        // If we got data back, there's a match
        if (data && data.arxiv_id) {
            return data;
        }
        
        return null;
    } catch (error) {
        console.error('Error checking paper hash:', error);
        return null;
    }
}

// PDF Hash Generation Function
async function generatePdfHash(pdfData) {
    try {
        // Ensure PDF.js is available
        if (!window.pdfjsLib) {
            throw new Error("PDF.js library not loaded");
        }
        
        // Create a buffer from the PDF data
        const pdfBuffer = await pdfData.arrayBuffer();
        
        // Load the PDF document
        const loadingTask = window.pdfjsLib.getDocument({data: pdfBuffer});
        const pdf = await loadingTask.promise;
        
        // Get text from first page only (for performance)
        const page = await pdf.getPage(1);
        const textContent = await page.getTextContent();
        
        // Extract the text
        const textItems = textContent.items.map(item => item.str);
        const text = textItems.join('');
        
        // Create hash string similar to Python implementation
        const hashStr = text.slice(0, 48).replace(/\s+/g, '').toLowerCase();
        
        // Log the hash to console
        console.log("PDF Hash:", hashStr);
        
        return hashStr;
    } catch (error) {
        console.error('Error generating PDF hash:', error);
        return null;
    }
}

// Utility function to sanitize arXiv IDs
function sanitizeArxivId(arxivId) {
    return arxivId.replace(/\//g, "-");
}

// Check if running on file:// protocol
function isFileProtocol() {
    return window.location.protocol === 'file:';
}

// Check if URL contains a paper ID
function checkForPaperInUrl() {
    const url = window.location.href;
    if (url.includes('/paper/')) {
        const paperIdMatch = url.match(/\/paper\/([^\/]+)$/);
        if (paperIdMatch && paperIdMatch[1]) {
            const paperId = paperIdMatch[1];
            fetchPaper(paperId);
        }
    }
}

// Initialize the app
function initApp() {
    // Load uploads from localStorage
    loadUploadsFromStorage();
    
    // Add event listeners
    setupEventListeners();
    
    // Check URL for paper ID
    checkForPaperInUrl();
}

// Set up event listeners
function setupEventListeners() {
    searchButton.addEventListener('click', handleSearch);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSearch();
    });
    sortBySelect.addEventListener('change', handleSortChange);
    prevPageButton.addEventListener('click', () => handlePageChange(-1));
    nextPageButton.addEventListener('click', () => handlePageChange(1));
    closeModal.addEventListener('click', () => errorModal.style.display = 'none');
    
    // Navigation tabs with API call checking
    document.getElementById('searchTab').addEventListener('click', () => {
        if (!isApiCallInProgress) {
            showSearchView();
        } else {
            showToast('Please wait for the current operation to complete', 'info');
        }
    });
    
    document.getElementById('uploadsTab').addEventListener('click', () => {
        if (!isApiCallInProgress) {
            showUploadsView();
        } else {
            showToast('Please wait for the current operation to complete', 'info');
        }
    });
    
    // Return to search button
    if (returnToSearchBtn) {
        returnToSearchBtn.addEventListener('click', () => {
            if (isApiCallInProgress) {
                showToast('Please wait for the current operation to complete', 'info');
                return;
            }
            
            if (currentView === 'uploads') {
                showUploadsView(); // Return to uploads view if that's where we came from
            } else {
                showSearchView(); // Otherwise return to search view
            }
            
            // Only attempt to update URL if not on file:// protocol
            if (!isFileProtocol()) {
                const url = window.location.href.split('/paper/')[0];
                window.history.pushState({}, '', url);
            }
        });
    }
    
    // Handle popstate (browser back/forward)
    window.addEventListener('popstate', (event) => {
        if (isApiCallInProgress) {
            // Prevent navigation during API calls
            showToast('Please wait for the current operation to complete', 'info');
            return;
        }
        
        const url = window.location.href;
        if (url.includes('/paper/')) {
            const paperIdMatch = url.match(/\/paper\/([^\/]+)$/);
            if (paperIdMatch && paperIdMatch[1]) {
                fetchPaper(paperIdMatch[1]);
            }
        } else {
            showSearchView();
        }
    });
    
    // Close modal when clicking outside
    window.addEventListener('click', (e) => {
        if (e.target === errorModal) {
            errorModal.style.display = 'none';
        }
    });
}

// Search handler
async function handleSearch() {
    if (isApiCallInProgress) {
        showToast('Please wait for the current operation to complete', 'info');
        return;
    }
    
    currentQuery = searchInput.value.trim();
    if (!currentQuery) {
        showToast('Please enter a search query', 'error');
        return;
    }
    
    // Skip fetch in showSearchView as we'll fetch directly
    showSearchView(true);
    
    currentPage = 0;
    await fetchResults();
}

// Sort handler
async function handleSortChange() {
    if (isApiCallInProgress) {
        showToast('Please wait for the current operation to complete', 'info');
        return;
    }
    
    currentSortBy = sortBySelect.value;
    currentPage = 0;
    
    // Only fetch results if we're in search view and have a query
    if (currentView === 'search' && currentQuery) {
        await fetchResults();
    }
}

// Page change handler
async function handlePageChange(delta) {
    if (isApiCallInProgress) {
        showToast('Please wait for the current operation to complete', 'info');
        return;
    }
    
    currentPage += delta;
    
    // Only fetch results if we're in search view
    if (currentView === 'search') {
        await fetchResults();
    }
}

// Fetch search results
async function fetchResults() {
    try {
        // Set API call in progress
        setApiCallState(true);
        
        // Show loading indicator
        searchLoadingIndicator.style.display = 'flex';
        resultsContainer.innerHTML = '';
        summarySection.style.display = 'none';
        summaryContent.innerHTML = '';
        
        const response = await fetch(`${SEARCH_ENDPOINT}?query=${encodeURIComponent(currentQuery)}&page=${currentPage}&sort_by=${currentSortBy}`);
        const data = await response.json();
        
        if (data.error) {
            showToast(data.error, 'error');
            return;
        }
        
        displayResults(data);
    } catch (error) {
        showToast('Failed to fetch results. Please try again.', 'error');
    } finally {
        // Hide loading indicator
        searchLoadingIndicator.style.display = 'none';
        
        // API call is complete
        setApiCallState(false);
    }
}

// Display search results
function displayResults(data) {
    // Only show pagination for search results
    show_pagination();
    
    // Clear the results container
    resultsContainer.innerHTML = '';
    
    // Add search results
    data.papers.forEach(paper => {
        // Only show actual search results (filter out manual uploads)
        if (!paper.arxiv_id || !paper.arxiv_id.startsWith('manual-upload-')) {
            const paperCard = createPaperCard(paper);
            resultsContainer.appendChild(paperCard);
        }
    });
    
    // Update pagination
    hasNextPage = data.has_next_page;
    prevPageButton.disabled = currentPage === 0;
    nextPageButton.disabled = !hasNextPage;
    pageInfo.textContent = `Page ${currentPage + 1}`;
}

function formatUploadDateTime(dateString) {
    const date = new Date(dateString);
    
    // Format time (HH:MM AM/PM)
    const hours = date.getHours();
    const minutes = date.getMinutes();
    const ampm = hours >= 12 ? 'PM' : 'AM';
    const formattedHours = hours % 12 || 12; // Convert 0 to 12 for 12 AM
    const formattedMinutes = minutes < 10 ? '0' + minutes : minutes;
    const timeStr = `${formattedHours}:${formattedMinutes} ${ampm}`;
    
    // Format date (MM/DD/YYYY)
    const day = date.getDate();
    const month = date.getMonth() + 1;
    const year = date.getFullYear();
    const formattedDay = day < 10 ? '0' + day : day;
    const formattedMonth = month < 10 ? '0' + month : month;
    // Changed order to month/day/year
    const dateStr = `${formattedMonth}/${formattedDay}/${year}`;
    
    return `${timeStr}, ${dateStr}`;
}

// Style for upload cards
function displayUploadsList() {
    // Clear the results container
    resultsContainer.innerHTML = '';
    
    // If no uploads, show a message
    if (myUploads.length === 0) {
        uploadCard.innerHTML = `
            <div class="upload-info">
                <h3 class="upload-title">${upload.title}</h3>
                <p class="upload-date">Uploaded on: ${formatUploadDateTime(upload.uploadDate)}</p>
            </div>
            <div class="upload-action">
                <div class="chevron-right"></div>
            </div>
        `;
        return;
    }
    
    // Create a container for uploads
    const uploadsContainer = document.createElement('div');
    uploadsContainer.className = 'uploads-list';
    
    // Add each upload as a card
    myUploads.forEach(upload => {
        const uploadCard = document.createElement('div');
        uploadCard.className = 'upload-card';
        
        uploadCard.innerHTML = `
            <div class="upload-info">
                <h3 class="upload-title">${upload.title}</h3>
                <p class="upload-date">Uploaded on: ${formatUploadDateTime(upload.uploadDate)}</p>
            </div>
            <div class="upload-action">
                <div class="chevron-right"></div>
            </div>
        `;
        
        // Add click handler to open the paper
        uploadCard.addEventListener('click', () => {
            if (!isApiCallInProgress) {
                processPaperSummary(upload);
            } else {
                showToast('Please wait for the current operation to complete', 'info');
            }
        });
        
        uploadsContainer.appendChild(uploadCard);
    });
    
    resultsContainer.appendChild(uploadsContainer);
}

// pagination is hidden at the beginning
function show_pagination() {
    const e = document.querySelector('.pagination');
    if (e) {
        // Only show pagination in search view AND when there's a query
        if (currentView === 'search' && currentQuery) {
            e.style.display = 'flex';
        } else {
            e.style.display = 'none';
        }
    }
}

// Create paper card
function createPaperCard(paper) {
    const card = document.createElement('div');
    card.className = 'paper-card';
    
    // Store original arXiv ID before sanitizing
    if (paper.arxiv_id) {
        paper.original_arxiv_id = paper.arxiv_id;
        paper.sanitized_arxiv_id = sanitizeArxivId(paper.arxiv_id);
    }
    
    card.innerHTML = `
        <h3 class="paper-title">${paper.title}</h3>
        <p class="paper-authors">${paper.authors.join(', ')}</p>
        <button class="summarize-button">
            <span class="button-text">Summarize</span>
            <span class="button-loader"></span>
        </button>
    `;
    
    // Add click handler for summarize button
    card.querySelector('.summarize-button').addEventListener('click', (event) => {
        if (isApiCallInProgress) {
            showToast('Please wait for the current operation to complete', 'info');
            return;
        }
        
        const button = event.currentTarget;
        // Set button to loading state
        setButtonLoading(button, true);
        
        const paperData = JSON.parse(button.getAttribute('data-paper') || '{}');
        if (!Object.keys(paperData).length) {
            // If data-paper attribute isn't set, set it
            button.setAttribute('data-paper', JSON.stringify(paper).replace(/'/g, "&apos;"));
            processPaperSummary(paper, button);
        } else {
            processPaperSummary(paperData, button);
        }
    });
    
    // Set the data-paper attribute
    card.querySelector('.summarize-button').setAttribute('data-paper', JSON.stringify(paper).replace(/'/g, "&apos;"));
    
    return card;
}

// Helper function to set button loading state
function setButtonLoading(button, isLoading) {
    if (isLoading) {
        button.classList.add('loading');
        button.disabled = true;
    } else {
        button.classList.remove('loading');
        button.disabled = false;
    }
}

// Check if summary exists and is not empty
function hasSummary(data) {
    return data && 
           data.summary !== undefined && 
           data.summary !== null && 
           data.summary.trim() !== '';
}

// Process paper summary request
async function processPaperSummary(paperData, buttonElement) {
    // Set API call in progress
    setApiCallState(true);
    
    // First, make sure we have a sanitized arxiv_id
    const originalArxivId = paperData.original_arxiv_id || paperData.arxiv_id;
    const sanitizedArxivId = paperData.sanitized_arxiv_id || sanitizeArxivId(paperData.arxiv_id);
    
    try {
        console.log(`Checking paper status for: ${sanitizedArxivId}`);
        
        // First check if the paper exists in the database using the paper endpoint
        const response = await fetch(`${PAPER_ENDPOINT}/${sanitizedArxivId}`);
        const data = await response.json();
        
        console.log('Paper endpoint response:', data);
        
        // Case 1: Paper exists with summary and not processing
        if (data && hasSummary(data) && data.processing === false) {
            console.log('Paper has summary, displaying...');
            
            // Store paper data for file:// protocol
            currentPaperData = data;
            
            try {
                // Only attempt to update URL if not on file:// protocol
                if (!isFileProtocol()) {
                    // Update URL with paper ID
                    const newUrl = `${window.location.origin}${window.location.pathname}/paper/${sanitizedArxivId}`;
                    window.history.pushState({}, '', newUrl);
                }
                
                // Display the paper view
                displayPaper(data);
            } catch (navError) {
                console.error('Navigation error:', navError);
                // If URL updating fails, still display the paper
                displayPaper(data);
            }
        }
        // Case 2: Paper is being processed
        else if (data && data.processing === true) {
            console.log('Paper is being processed...');
            showToast('The paper is being summarized. Please check back later.', 'info');
        }
        // Case 3: Paper doesn't exist in DB or has error response
        else if (!data || data.message && data.message.includes("No data found")) {
            console.log('Paper not found, enqueueing...');
            
            // Enqueue the paper for summarization
            await enqueuePaper(paperData);
            showToast('Paper has been queued for summarizing', 'success');
        }
        // Case 4: Other cases
        else {
            console.log('Unknown paper state:', data);
            showToast('Could not summarize paper', 'error');
        }
    } catch (error) {
        console.error('Error processing paper:', error);
        showToast('Could not summarize paper', 'error');
    } finally {
        // Reset button state in case of error
        if (buttonElement) {
            setButtonLoading(buttonElement, false);
        }
        
        // API call is complete
        setApiCallState(false);
    }
}

// Enqueue paper for summarization
async function enqueuePaper(paperData) {
    // We don't set API call state here because it's called from processPaperSummary
    // which already sets the API call state
    
    try {
        // Use the original paper data for enqueueing - don't modify it
        const response = await fetch(SUMMARIZE_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(paperData)
        });
        
        const data = await response.json();
        
        if (data.error) {
            console.error('Error enqueueing paper:', data.error);
            return false;
        }
        
        return true;
    } catch (error) {
        console.error('Error enqueueing paper:', error);
        return false;
    }
}

// Fetch paper by ID
async function fetchPaper(arxivId) {
    // Set API call in progress
    setApiCallState(true);
    
    try {
        showToast('Loading paper...', 'info');
        
        // For file:// protocol, use stored paper data if available
        if (isFileProtocol() && currentPaperData) {
            displayPaper(currentPaperData);
            return;
        }
        
        // Check if the paper exists using the paper endpoint
        const response = await fetch(`${PAPER_ENDPOINT}/${arxivId}`);
        const data = await response.json();
        
        console.log('Fetch paper response:', data);
        
        // Case 1: Paper exists with summary and not processing
        if (data && hasSummary(data) && data.processing === false) {
            displayPaper(data);
        }
        // Case 2: Paper is being processed
        else if (data && data.processing === true) {
            showSearchView();
            showToast('The paper is being summarized. Please check back later.', 'info');
        }
        // Case 3: Paper doesn't exist in DB
        else {
            showSearchView();
            showToast('Paper not found or not yet summarized.', 'error');
        }
    } catch (error) {
        console.error('Error fetching paper:', error);
        showSearchView();
        showToast('Could not summarize paper', 'error');
    } finally {
        // API call is complete
        setApiCallState(false);
    }
}

// Display paper in paper view
function displayPaper(paperData) {
    // Get the summary from the correct location in the data structure
    let summary = '';
    if (paperData.summary) {
        summary = paperData.summary;
    } else if (paperData.arxivReference && paperData.arxivReference.summary) {
        summary = paperData.arxivReference.summary;
    }
    
    // Convert markdown to HTML for the summary
    const summaryHtml = summary
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')  // Bold
        .replace(/\*(.*?)\*/g, '<em>$1</em>')  // Italic
        .replace(/\n/g, '<br>');  // Line breaks
    
    // Get authors - either from the paper data or from arxivReference
    let authors = [];
    if (paperData.authors) {
        authors = paperData.authors;
    } else if (paperData.arxivReference && paperData.arxivReference.authors) {
        authors = paperData.arxivReference.authors;
    }
    
    // Get title - either from the paper data or from arxivReference
    let title = paperData.title || '';
    if (!title && paperData.arxivReference && paperData.arxivReference.title) {
        title = paperData.arxivReference.title;
    }
    
    // Populate paper content
    paperContent.innerHTML = `
        <h1>${title}</h1>
        <p class="paper-authors">${Array.isArray(authors) ? authors.join(', ') : ''}</p>
        <div class="paper-summary">${summaryHtml}</div>
    `;
    
    // Show paper view, hide search view
    showPaperView();
}

// Show search view
function showSearchView(skipFetch = false) {
    currentView = 'search';
    paperView.style.display = 'none';
    searchSection.style.display = 'block';
    resultsSection.style.display = 'block';
    summarySection.style.display = 'none';
    
    // Show pagination for search results
    const paginationElement = document.querySelector('.pagination');
    if (paginationElement) {
        paginationElement.style.display = 'flex';
    }
    
    // Update the active tab
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById('searchTab').classList.add('active');
    
    // Only fetch if not skipped and we have a query
    if (!skipFetch && currentQuery && !isApiCallInProgress) {
        fetchResults();
    } else if (!currentQuery) {
        // Clear the results container if no search has been performed
        resultsContainer.innerHTML = '';
    }
    show_pagination();
}

// Show uploads view
function showUploadsView() {
    currentView = 'uploads';
    paperView.style.display = 'none';
    
    // Hide search bar and filters, but keep results section visible
    searchSection.style.display = 'none';
    resultsSection.style.display = 'block';
    summarySection.style.display = 'none';
    
    // Clear the search input field
    if (searchInput) {
        searchInput.value = '';
    }
    
    // Add this line to reset the currentQuery variable
    currentQuery = '';
    
    // Hide pagination for uploads view
    const paginationElement = document.querySelector('.pagination');
    if (paginationElement) {
        paginationElement.style.display = 'none';
    }
    
    // Update the active tab
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById('uploadsTab').classList.add('active');
    
    // Display uploads
    displayUploadsList();
}

// Show paper view
function showPaperView() {
    currentView = 'paper';
    paperView.style.display = 'block';
    searchSection.style.display = 'none';
    resultsSection.style.display = 'none';
    summarySection.style.display = 'none';
}

// Display toast notification
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    
    toastContainer.appendChild(toast);
    
    // Show toast
    setTimeout(() => {
        toast.classList.add('show');
    }, 100);
    
    // Hide and remove toast after 5 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            if (toastContainer.contains(toast)) {
                toastContainer.removeChild(toast);
            }
        }, 300);
    }, 5000);
}

// Show error modal
function showError(message) {
    errorMessage.textContent = message;
    errorModal.style.display = 'block';
}

// Disable UI interactions
function disableUIInteractions() {
    searchInput.disabled = true;
    searchButton.disabled = true;
    sortBySelect.disabled = true;
    prevPageButton.disabled = true;
    nextPageButton.disabled = true;
    
    // Disable existing summarize buttons
    document.querySelectorAll('.summarize-button').forEach(button => {
        button.disabled = true;
    });
}

// Enable UI interactions
function enableUIInteractions() {
    searchInput.disabled = false;
    searchButton.disabled = false;
    sortBySelect.disabled = false;
    
    // Re-enable pagination buttons (respecting their state)
    prevPageButton.disabled = currentPage === 0;
    nextPageButton.disabled = !hasNextPage;
    
    // Re-enable summarize buttons
    document.querySelectorAll('.summarize-button').forEach(button => {
        if (!button.classList.contains('loading')) {
            button.disabled = false;
        }
    });
}

// Disable all UI interactions
function disableAllUIInteractions() {
    // Get all buttons and inputs
    const buttons = document.querySelectorAll('button:not(.close)');
    const inputs = document.querySelectorAll('input');
    const selects = document.querySelectorAll('select');
    
    // Disable all interactive elements
    buttons.forEach(button => { button.disabled = true; });
    inputs.forEach(input => { input.disabled = true; });
    selects.forEach(select => { select.disabled = true; });
}

// Enable all UI interactions
function enableAllUIInteractions() {
    // Get all buttons and inputs
    const buttons = document.querySelectorAll('button:not(.close)');
    const inputs = document.querySelectorAll('input');
    const selects = document.querySelectorAll('select');
    
    // Enable all elements first
    buttons.forEach(button => { button.disabled = false; });
    inputs.forEach(input => { input.disabled = false; });
    selects.forEach(select => { select.disabled = false; });
    
    // Then apply specific state rules
    if (window.prevPageButton) window.prevPageButton.disabled = window.currentPage === 0;
    if (window.nextPageButton) window.nextPageButton.disabled = !window.hasNextPage;
    
    // Re-enable summarize buttons that aren't loading
    document.querySelectorAll('.summarize-button').forEach(button => {
        if (!button.classList.contains('loading')) {
            button.disabled = false;
        }
    });
}

// Modified file upload function with PDF hash generation
async function uploadFile() {
    const input = document.getElementById("uploadInput");
    const file = input.files[0];
    if (!file) {
        showToast("Please select a file", "error");
        return;
    }
    
    // Set API call in progress
    setApiCallState(true);
    
    // Set button to loading state
    setUploadButtonLoading(true);
    
    // Show upload progress modal
    const uploadModal = document.getElementById("uploadModal");
    const uploadStep1 = document.getElementById("uploadStep1");
    const uploadStep2 = document.getElementById("uploadStep2");
    const uploadStep3 = document.getElementById("uploadStep3");
    const uploadStatus = document.getElementById("uploadStatus");
    
    uploadModal.style.display = "block";
    
    const extension = file.name.split('.').pop().toLowerCase();
    const fileName = `${Date.now()}_${file.name.replace(/\.[^/.]+$/, "")}.pdf`;
    const uploadUrl = `https://file-upload-papergist.s3.amazonaws.com/${fileName}`;
    let pdfBlob;
    
    try {
        // Step 1: Reading file
        uploadStatus.textContent = "Reading file...";
        
        if (extension === 'pdf') {
            // For PDF files, generate hash before processing
            const pdfHash = await generatePdfHash(file);
            console.log("Generated PDF Hash:", pdfHash);
            
            // Check if the hash exists in the database
            if (pdfHash) {
                const matchingPaper = await checkPaperHashExists(pdfHash);
                
                if (matchingPaper) {
                    // Close upload modal
                    uploadModal.style.display = "none";
                    resetUploadSteps();
                    
                    // Show toast notification
                    showToast("Existing summary found for uploaded file", "success");
                    
                    // Display the paper view
                    currentPaperData = matchingPaper;
                    
                    try {
                        // Only attempt to update URL if not on file:// protocol
                        if (!isFileProtocol() && matchingPaper.sanitized_arxiv_id) {
                            // Update URL with paper ID
                            const newUrl = `${window.location.origin}${window.location.pathname}/paper/${matchingPaper.sanitized_arxiv_id}`;
                            window.history.pushState({}, '', newUrl);
                        }
                        
                        // Display the paper
                        displayPaper(matchingPaper);
                        
                        // Clear the file input
                        input.value = "";
                        
                        return; // Exit early, don't continue with upload
                    } catch (navError) {
                        console.error('Navigation error:', navError);
                        // If URL updating fails, still display the paper
                        displayPaper(matchingPaper);
                        
                        // Clear the file input
                        input.value = "";
                        
                        return; // Exit early, don't continue with upload
                    }
                }
            }
            
            pdfBlob = file;
            
            // Move to step 2 (skip conversion for PDF)
            uploadStep1.classList.remove("active");
            uploadStep1.classList.add("completed");
            uploadStep3.classList.add("active");
            uploadStatus.textContent = "Uploading to server...";
            
        } else if (extension === 'docx') {
            // Move to step 2
            uploadStep1.classList.remove("active");
            uploadStep1.classList.add("completed");
            uploadStep2.classList.add("active");
            uploadStatus.textContent = "Converting DOCX to PDF...";
            
            const arrayBuffer = await file.arrayBuffer();
            const result = await mammoth.convertToHtml({ arrayBuffer });
            const html = result.value;
            pdfBlob = await convertHtmlToPdfBlob(html);
            
            // Generate hash for the converted PDF
            const pdfHash = await generatePdfHash(pdfBlob);
            console.log("Generated PDF Hash from DOCX:", pdfHash);
            
            // Check if the hash exists in the database
            if (pdfHash) {
                const matchingPaper = await checkPaperHashExists(pdfHash);
                
                if (matchingPaper) {
                    // Close upload modal
                    uploadModal.style.display = "none";
                    resetUploadSteps();
                    
                    // Show toast notification
                    showToast("Existing summary found for uploaded file", "success");
                    
                    // Display the paper view
                    currentPaperData = matchingPaper;
                    
                    try {
                        // Only attempt to update URL if not on file:// protocol
                        if (!isFileProtocol() && matchingPaper.sanitized_arxiv_id) {
                            // Update URL with paper ID
                            const newUrl = `${window.location.origin}${window.location.pathname}/paper/${matchingPaper.sanitized_arxiv_id}`;
                            window.history.pushState({}, '', newUrl);
                        }
                        
                        // Display the paper
                        displayPaper(matchingPaper);
                        
                        // Clear the file input
                        input.value = "";
                        
                        return; // Exit early, don't continue with upload
                    } catch (navError) {
                        console.error('Navigation error:', navError);
                        // If URL updating fails, still display the paper
                        displayPaper(matchingPaper);
                        
                        // Clear the file input
                        input.value = "";
                        
                        return; // Exit early, don't continue with upload
                    }
                }
            }
            
            // Move to step 3
            uploadStep2.classList.remove("active");
            uploadStep2.classList.add("completed");
            uploadStep3.classList.add("active");
            uploadStatus.textContent = "Uploading to server...";
            
        } else if (extension === 'txt') {
            // Move to step 2
            uploadStep1.classList.remove("active");
            uploadStep1.classList.add("completed");
            uploadStep2.classList.add("active");
            uploadStatus.textContent = "Converting TXT to PDF...";
            
            const text = await file.text();
            const html = `<pre style="font-family:monospace; white-space: pre-wrap;">${text}</pre>`;
            pdfBlob = await convertHtmlToPdfBlob(html);
            
            // Generate hash for the converted PDF
            const pdfHash = await generatePdfHash(pdfBlob);
            console.log("Generated PDF Hash from TXT:", pdfHash);
            
            // Check if the hash exists in the database
            if (pdfHash) {
                const matchingPaper = await checkPaperHashExists(pdfHash);
                
                if (matchingPaper) {
                    // Close upload modal
                    uploadModal.style.display = "none";
                    resetUploadSteps();
                    
                    // Show toast notification
                    showToast("Existing summary found for uploaded file", "success");
                    
                    // Display the paper view
                    currentPaperData = matchingPaper;
                    
                    try {
                        // Only attempt to update URL if not on file:// protocol
                        if (!isFileProtocol() && matchingPaper.sanitized_arxiv_id) {
                            // Update URL with paper ID
                            const newUrl = `${window.location.origin}${window.location.pathname}/paper/${matchingPaper.sanitized_arxiv_id}`;
                            window.history.pushState({}, '', newUrl);
                        }
                        
                        // Display the paper
                        displayPaper(matchingPaper);
                        
                        // Clear the file input
                        input.value = "";
                        
                        return; // Exit early, don't continue with upload
                    } catch (navError) {
                        console.error('Navigation error:', navError);
                        // If URL updating fails, still display the paper
                        displayPaper(matchingPaper);
                        
                        // Clear the file input
                        input.value = "";
                        
                        return; // Exit early, don't continue with upload
                    }
                }
            }
            
            // Move to step 3
            uploadStep2.classList.remove("active");
            uploadStep2.classList.add("completed");
            uploadStep3.classList.add("active");
            uploadStatus.textContent = "Uploading to server...";
            
        } else {
            uploadModal.style.display = "none";
            showToast("❌ Unsupported file type. Please upload PDF, DOCX, or TXT.", "error");
            return;
        }
        
        // Step 3: Upload to S3
        const res = await fetch(uploadUrl, {
            method: "PUT",
            headers: {
                "Content-Type": "application/pdf"
            },
            body: pdfBlob
        });
        
        if (res.ok) {
            const fileUrl = `https://file-upload-papergist.s3.amazonaws.com/${fileName}`;
            
            // Mark step 3 as completed
            uploadStep3.classList.remove("active");
            uploadStep3.classList.add("completed");
            uploadStatus.textContent = "Upload complete!";
            
            // Create a dummy arXiv object for the manually uploaded file
            const arxivId = `manual-upload-${generateUUID()}`;
            const sanitizedArxivId = arxivId;
            const uploadDate = new Date();
            
            const dummyPaperData = {
                arxiv_id: arxivId,
                sanitized_arxiv_id: sanitizedArxivId,
                original_arxiv_id: arxivId,
                title: `Upload ID: ${arxivId}`,
                authors: ["Manually uploaded"],
                primary_category: "Manually uploaded",
                categories: ["Manually uploaded"],
                published: uploadDate.toISOString(),
                updated: uploadDate.toISOString(),
                pdf_url: fileUrl,
                summary: "This document was manually uploaded and is being processed for summarization.",
                processing: true
            };
            
            // Add to myUploads
            const uploadRecord = {
                arxiv_id: arxivId,
                sanitized_arxiv_id: sanitizedArxivId,
                title: `Upload ID: ${arxivId}`,
                uploadDate: uploadDate.toISOString(),
                fileUrl: fileUrl,
                fileName: file.name
            };
            
            addUploadToStorage(uploadRecord);
            
            // Enqueue for summarization
            try {
                await enqueuePaper(dummyPaperData);
                showToast("Paper has been queued for summarization", "success");
            } catch (enqueueErr) {
                console.error("Error enqueueing paper:", enqueueErr);
                showToast("There was an issue queuing the paper for summarization", "error");
            }
            
            // Close modal after a short delay
            setTimeout(() => {
                uploadModal.style.display = "none";
                resetUploadSteps();
                showToast(`File uploaded successfully! ${file.name}`, "success");
                console.log("Public File URL:", fileUrl);
                
                // Show uploads tab after successful upload
                showUploadsView();
            }, 1000);
        } else {
            throw new Error("Upload failed");
        }
    } catch (err) {
        console.error("Upload error", err);
        uploadModal.style.display = "none";
        showToast("❌ Upload error: " + (err.message || "Unknown error"), "error");
    } finally {
        // Reset button state
        setUploadButtonLoading(false);
        
        // API call is complete
        setApiCallState(false);
        
        // Clear the file input
        input.value = "";
    }
}

// Reset upload steps for next upload
function resetUploadSteps() {
    const steps = document.querySelectorAll('.upload-step');
    steps.forEach(step => {
        step.classList.remove('active', 'completed');
    });
    document.getElementById('uploadStep1').classList.add('active');
    document.getElementById('uploadStatus').textContent = 'Please wait...';
}

async function convertHtmlToPdfBlob(html) {
    const container = document.createElement("div");
    container.innerHTML = html;
    document.body.appendChild(container);
    return await html2pdf().from(container).outputPdf("blob").then(blob => {
        document.body.removeChild(container);
        return blob;
    });
}

// Set upload button loading state
function setUploadButtonLoading(isLoading) {
    const uploadButton = document.getElementById('uploadButton');
    if (isLoading) {
        uploadButton.classList.add('loading');
        uploadButton.disabled = true;
    } else {
        uploadButton.classList.remove('loading');
        uploadButton.disabled = false;
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initApp();
    
    // Set up event listeners for file upload
    const uploadButton = document.getElementById('uploadButton');
    const uploadInput = document.getElementById('uploadInput');
    
    uploadButton.addEventListener('click', function() {
        if (!isApiCallInProgress) {
            uploadInput.click();
        } else {
            showToast('Please wait for the current operation to complete', 'info');
        }
    });
    
    uploadInput.addEventListener('change', uploadFile);
});
