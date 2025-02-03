document.addEventListener('DOMContentLoaded', function() {
    const sidebarLinks = document.querySelectorAll('.sidebar-link');
    sidebarLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            if (this.getAttribute('href').startsWith('#')) {
                e.preventDefault();
                const targetId = this.getAttribute('href').substring(1);
                const targetElement = document.getElementById(targetId);
                if (targetElement) {
                    targetElement.scrollIntoView({ behavior: 'smooth' });
                }
            }
        });
    });
    
    // Student Search
    const searchForm = document.getElementById('student-search-form');
    const studentInfo = document.getElementById('student-info');

    searchForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const studentId = document.getElementById('student-id').value;
        // Here you would typically make an AJAX call to your Flask backend
        // For now, we'll just show the student info section
        studentInfo.classList.remove('hidden');
    });

    // Custom Course Recommendations
    const customCourseForm = document.getElementById('custom-courses-form');
    const customCourseList = document.getElementById('custom-course-list');

    customCourseForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const courseInput = document.getElementById('course-input');
        const course = courseInput.value;
        if (course) {
            const li = document.createElement('li');
            li.textContent = course;
            customCourseList.appendChild(li);
            courseInput.value = '';
        }
    });

    // Send Advising Report
    const sendReportBtn = document.getElementById('send-report');
    sendReportBtn.addEventListener('click', function() {
        alert('Advising report sent successfully!');
    });

    // Floating Action Button
    const fab = document.getElementById('fab');
    const chatRoom = document.getElementById('chat-room');
    fab.addEventListener('click', function() {
        chatRoom.classList.toggle('hidden');
    });

    // Close Chat
    const closeChat = document.getElementById('close-chat');
    closeChat.addEventListener('click', function() {
        chatRoom.classList.add('hidden');
    });

    // Send Chat Message
    const chatForm = document.getElementById('chat-form');
    const chatMessages = document.getElementById('chat-messages');
    chatForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const chatInput = document.getElementById('chat-input');
        const message = chatInput.value;
        if (message) {
            const div = document.createElement('div');
            div.textContent = `Advisor: ${message}`;
            chatMessages.appendChild(div);
            chatInput.value = '';
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    });

    // Here you would typically add more JavaScript to handle:
    // - Calendar functionality for setting availability
    // - Displaying and managing appointments
    // - Real-time chat functionality
    // - AJAX calls to your Flask backend for various operations
});