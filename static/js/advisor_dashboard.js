document.addEventListener('DOMContentLoaded', function() {
    // Availability Form
    const availabilityForm = document.getElementById('availability-form');
    const availabilitySlots = document.getElementById('availability-slots');

    availabilityForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const date = document.getElementById('slot-date').value;
        const startTime = document.getElementById('slot-start-time').value;
        const endTime = document.getElementById('slot-end-time').value;

        // Create slot element
        const slotDiv = document.createElement('div');
        slotDiv.className = 'slot-item';
        
        // Format the date and time
        const formattedDate = new Date(date).toLocaleDateString();
        slotDiv.innerHTML = `
            ${formattedDate} ${startTime} - ${endTime}
            <button onclick="this.parentElement.remove()">Delete</button>
        `;
        
        availabilitySlots.appendChild(slotDiv);
        availabilityForm.reset();
    });

    // Student Search Form
    const studentSearchForm = document.getElementById('student-search-form');
    const studentInfo = document.getElementById('student-info');

    studentSearchForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const studentId = document.getElementById('student-id').value;
        
        // In a real application, this would fetch student data from the server
        // For now, we'll just show some mock data
        studentInfo.innerHTML = `
            <div style="border: 1px solid #000; padding: 10px; margin-top: 15px;">
                <h4>Student ID: ${studentId}</h4>
                <p>Name: John Doe</p>
                <p>GPA: 3.5</p>
                <p>Major: Computer Science</p>
            </div>
        `;
    });

    // Chat Form
    const chatForm = document.getElementById('chat-form');
    const chatMessages = document.getElementById('chat-messages');

    chatForm.addEventListener('submit', function(e) {
        e.preventDefault();
        const messageInput = document.getElementById('message');
        const message = messageInput.value;
        
        if (message.trim()) {
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message';
            messageDiv.textContent = `Advisor: ${message}`;
            chatMessages.appendChild(messageDiv);
            messageInput.value = '';
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    });
});