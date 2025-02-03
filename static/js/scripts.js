document.addEventListener('DOMContentLoaded', function() {
    // Add any global JavaScript functionality here

    // Example: Smooth scrolling for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();

            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });

    // Example: Toggle mobile menu
    const menuToggle = document.createElement('button');
    menuToggle.classList.add('menu-toggle');
    menuToggle.innerHTML = '☰';
    document.querySelector('.navbar').prepend(menuToggle);

    menuToggle.addEventListener('click', function() {
        document.querySelector('.navbar-menu').classList.toggle('active');
    });
});