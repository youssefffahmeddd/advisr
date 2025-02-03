document.addEventListener('DOMContentLoaded', function() {
    // Smooth scrolling and active navigation
    initNavigation();

    // Animate progress bar
    animateProgressBar();

    // Initialize chat functionality
    initChat();

    // Initialize dynamic content loading
    initDynamicContent();

    // Initialize chat popup functionality
    initChatPopup();
});

function initNavigation() {
    const navLinks = document.querySelectorAll('.nav-links a');
    const sections = document.querySelectorAll('.dashboard-section');

    function setActiveNavItem() {
        let currentSection = '';
        sections.forEach(section => {
            const sectionTop = section.offsetTop;
            const sectionHeight = section.clientHeight;
            if (window.pageYOffset >= sectionTop - 60) {
                currentSection = section.id;
            }
        });

        navLinks.forEach(link => {
            link.classList.remove('active');
            if (link.getAttribute('href').slice(1) === currentSection) {
                link.classList.add('active');
            }
        });
    }

    window.addEventListener('scroll', setActiveNavItem);
    setActiveNavItem();

    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const targetId = this.getAttribute('href').slice(1);
            const targetSection = document.getElementById(targetId);
            window.scrollTo({
                top: targetSection.offsetTop - 20,
                behavior: 'smooth'
            });
        });
    });
}

function animateProgressBar() {
    const progressBar = document.querySelector('.progress');
    if (progressBar) {
        const percentage = progressBar.getAttribute('data-percentage');
        progressBar.style.width = '0%';
        setTimeout(() => {
            progressBar.style.width = percentage + '%';
        }, 500);
    }
}

function initChat() {
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');

    if (chatForm && chatInput && chatMessages) {
        chatForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const message = chatInput.value.trim();
            if (message) {
                addChatMessage('You', message);
                chatInput.value = '';
                // Send message to server
                sendChatMessage(message);
            }
        });
    }
}

function addChatMessage(sender, message) {
    const chatMessages = document.getElementById('chat-messages');
    if (chatMessages) {
        const messageElement = document.createElement('div');
        messageElement.className = 'chat-message';
        messageElement.innerHTML = `<strong>${sender}:</strong> ${message}`;
        chatMessages.appendChild(messageElement);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
}

function sendChatMessage(message) {
    // Implement actual server communication here
    fetch('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: message }),
    })
    .then(response => response.json())
    .then(data => {
        addChatMessage('Advisor', data.response);
    })
    .catch(error => {
        console.error('Error:', error);
        addChatMessage('System', 'Sorry, there was an error sending your message.');
    });
}

function initDynamicContent() {
    // Load transcript data
    loadTranscript();

    // Load recommended courses
    loadRecommendedCourses();

    // Load advisor slots
    loadAdvisorSlots();

    // Initialize real-time updates
    initRealTimeUpdates();
}

function loadTranscript() {
    // Parse transcript data from the embedded JSON
    const transcriptData = JSON.parse(document.getElementById('transcript-data').textContent);
    console.log("Transcript Data:", transcriptData); // Debugging log
    const transcriptBody = document.querySelector('#transcript .data-table tbody');
    transcriptBody.innerHTML = ''; // Clear the table

    transcriptData.forEach(course => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${course.course_code}</td>
            <td>${course.course_name}</td>
            <td>${course.course_type}</td>
            <td>${course.credit_hours}</td>
            <td>${course.grade}</td>
            <td>${course.points}</td>
            <td>${course.repetition_count}</td>
        `;
        transcriptBody.appendChild(row);
    });
}

function loadRecommendedCourses() {
    // Get the recommended courses from a pre-rendered script tag
    const recommendedCoursesData = JSON.parse(document.getElementById('recommended-courses-data').textContent);

    // Select the table body where courses will be rendered
    const coursesBody = document.querySelector('#recommendations .data-table tbody');
    coursesBody.innerHTML = '';

    // Loop through the recommended courses data and create table rows
    recommendedCoursesData.forEach(course => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${course.course_code}</td>
            <td>${course.course_name}</td>
            <td>${course.credit_hours}</td>
        `;
        coursesBody.appendChild(row);
    });
}

function loadAdvisorSlots() {
    fetch('/api/advisor-slots')
        .then(response => response.json())
        .then(data => {
            const slotsBody = document.querySelector('#advisor-slots .data-table tbody');
            slotsBody.innerHTML = '';
            data.forEach(slot => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${slot.Date}</td>
                    <td>${slot.Start_Time}</td>
                    <td>${slot.End_Time}</td>
                    <td>
                        <form action="/reserve-slot" method="post">
                            <input type="hidden" name="slot_id" value="${slot.Slot_ID}">
                            <button type="submit" class="btn-reserve">Reserve</button>
                        </form>
                    </td>
                `;
                slotsBody.appendChild(row);
            });
        })
        .catch(error => console.error('Error loading advisor slots:', error));
}

function initRealTimeUpdates() {
    // Implement WebSocket or Server-Sent Events for real-time updates
    const eventSource = new EventSource('/api/updates');

    eventSource.onmessage = function(event) {
        const data = JSON.parse(event.data);
        switch(data.type) {
            case 'gpa_update':
                updateGPA(data.gpa);
                break;
            case 'progress_update':
                updateProgress(data.progress);
                break;
            case 'new_message':
                addChatMessage('Advisor', data.message);
                break;
            // Add more cases as needed
        }
    };

    eventSource.onerror = function(error) {
        console.error('EventSource failed:', error);
        eventSource.close();
    };
}

function updateGPA(gpa) {
    const gpaElement = document.querySelector('.student-info .info-item:nth-child(2) .value');
    if (gpaElement) {
        gpaElement.textContent = gpa;
        gpaElement.classList.add('updated');
        setTimeout(() => gpaElement.classList.remove('updated'), 3000);
    }
}

function updateProgress(progress) {
    const progressBar = document.querySelector('.progress');
    const progressText = document.querySelector('.progress-text');
    if (progressBar && progressText) {
        progressBar.style.width = `${progress}%`;
        progressText.textContent = `${progress}% Complete`;
        progressText.classList.add('updated');
        setTimeout(() => progressText.classList.remove('updated'), 3000);
    }
}

function initChatPopup() {
    const openChatBtn = document.getElementById('open-chat');
    const closeChatBtn = document.getElementById('close-chat');
    const chatPopup = document.getElementById('chat-popup');

    openChatBtn.addEventListener('click', () => {
        chatPopup.style.display = 'block';
        openChatBtn.style.display = 'none';
    });

    closeChatBtn.addEventListener('click', () => {
        chatPopup.style.display = 'none';
        openChatBtn.style.display = 'block';
    });
}

console.log('Interactive Dashboard JavaScript loaded successfully!');

