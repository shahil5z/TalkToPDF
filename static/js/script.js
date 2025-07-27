document.addEventListener('DOMContentLoaded', function() {
    // Theme Toggle
    const themeToggle = document.getElementById('themeToggle');
    const body = document.body;
    const savedTheme = localStorage.getItem('theme') || 'light';
    if (savedTheme === 'dark') {
        body.classList.add('dark-theme');
        themeToggle.checked = true;
    }

    themeToggle.addEventListener('change', function() {
        if (this.checked) {
            body.classList.add('dark-theme');
            localStorage.setItem('theme', 'dark');
        } else {
            body.classList.remove('dark-theme');
            localStorage.setItem('theme', 'light');
        }
    });

    // Loading Spinner
    const uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function() {
            document.getElementById('loadingSpinner').classList.remove('d-none');
        });
    }

    // Auto-close alerts
    setTimeout(function() {
        let alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            new bootstrap.Alert(alert).close();
        });
    }, 5000);

    // Ensure accordion collapses work smoothly
    const accordions = document.querySelectorAll('.accordion-button');
    accordions.forEach(button => {
        button.addEventListener('click', function() {
            const collapseTarget = document.querySelector(this.getAttribute('data-bs-target'));
            if (collapseTarget.classList.contains('show')) {
                this.classList.add('collapsed');
            } else {
                this.classList.remove('collapsed');
            }
        });
    });

    // Chat Functionality
    const chatForm = document.getElementById('chatForm');
    const chatInput = document.getElementById('chatInput');
    const chatHistory = document.getElementById('chatHistory');

    if (chatForm && chatInput && chatHistory) {
        // Initialize MutationObserver to detect DOM changes in chatHistory
        const observer = new MutationObserver((mutations) => {
            if (mutations.some(mutation => mutation.addedNodes.length > 0)) {
                const chatBody = document.querySelector('.chat-body');
                chatBody.scrollTo({
                    top: chatBody.scrollHeight,
                    behavior: 'smooth'
                });
            }
        });
        observer.observe(chatHistory, { childList: true });

        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            sendMessage();
        });
    }

    function sendMessage() {
        const question = chatInput.value.trim();
        if (!question) return;

        // Append user message
        const userMessage = document.createElement('div');
        userMessage.className = 'chat-message';
        userMessage.textContent = question;
        chatHistory.appendChild(userMessage);

        // Clear input
        chatInput.value = '';

        // Show loading indicator
        const loading = document.createElement('div');
        loading.className = 'chat-message text-muted';
        loading.textContent = 'Loading...';
        chatHistory.appendChild(loading);

        // Send AJAX request
        fetch('/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: 'question=' + encodeURIComponent(question)
        })
        .then(response => response.json())
        .then(data => {
            // Remove loading indicator
            chatHistory.removeChild(loading);

            if (data.error) {
                const errorMessage = document.createElement('div');
                errorMessage.className = 'chat-response error-message';
                errorMessage.textContent = 'Error: ' + data.error;
                chatHistory.appendChild(errorMessage);
            } else {
                const responseMessage = document.createElement('div');
                responseMessage.className = 'chat-response';
                responseMessage.textContent = data.answer;
                chatHistory.appendChild(responseMessage);
            }
        })
        .catch(error => {
            // Remove loading indicator
            chatHistory.removeChild(loading);

            const errorMessage = document.createElement('div');
            errorMessage.className = 'chat-response error-message';
            errorMessage.textContent = 'Error: Failed to get response.';
            chatHistory.appendChild(errorMessage);
        });
    }
});