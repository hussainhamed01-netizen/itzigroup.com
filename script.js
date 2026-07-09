/* ============================================
   ITZIGROUP — TECH FOR FUTURE
   Main JavaScript — Interactions & Effects
   ============================================ */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize all modules
    initNavbar();
    initMobileNav();
    initSmoothScroll();
    initScrollReveal();
    initParticles();
    initCursorGlow();
    initCountUp();
    initContactForm();
    initActiveNavHighlight();
});

/* ============================================
   NAVBAR — Scroll Effect
   ============================================ */
function initNavbar() {
    const navbar = document.getElementById('navbar');
    let lastScroll = 0;

    window.addEventListener('scroll', () => {
        const currentScroll = window.pageYOffset;

        if (currentScroll > 50) {
            navbar.classList.add('scrolled');
        } else {
            navbar.classList.remove('scrolled');
        }

        lastScroll = currentScroll;
    }, { passive: true });
}

/* ============================================
   MOBILE NAVIGATION
   ============================================ */
function initMobileNav() {
    const toggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');

    toggle.addEventListener('click', () => {
        toggle.classList.toggle('active');
        navLinks.classList.toggle('active');
        document.body.style.overflow = navLinks.classList.contains('active') ? 'hidden' : '';
    });

    // Close menu when clicking a link
    navLinks.querySelectorAll('.nav-link').forEach(link => {
        link.addEventListener('click', () => {
            toggle.classList.remove('active');
            navLinks.classList.remove('active');
            document.body.style.overflow = '';
        });
    });
}

/* ============================================
   SMOOTH SCROLL
   ============================================ */
function initSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
            }
        });
    });
}

/* ============================================
   SCROLL REVEAL (Custom AOS)
   ============================================ */
function initScrollReveal() {
    const elements = document.querySelectorAll('[data-aos]');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const delay = entry.target.getAttribute('data-aos-delay') || 0;
                setTimeout(() => {
                    entry.target.classList.add('aos-animate');
                }, parseInt(delay));
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    });

    elements.forEach(el => observer.observe(el));
}

/* ============================================
   ACTIVE NAV HIGHLIGHT
   ============================================ */
function initActiveNavHighlight() {
    const sections = document.querySelectorAll('section[id]');
    const navLinks = document.querySelectorAll('.nav-link');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('id');
                navLinks.forEach(link => {
                    link.classList.remove('active');
                    if (link.getAttribute('href') === `#${id}`) {
                        link.classList.add('active');
                    }
                });
            }
        });
    }, {
        threshold: 0.3,
        rootMargin: '-80px 0px -50% 0px'
    });

    sections.forEach(section => observer.observe(section));
}

/* ============================================
   PARTICLE SYSTEM
   ============================================ */
function initParticles() {
    const canvas = document.getElementById('particleCanvas');
    const ctx = canvas.getContext('2d');
    let particles = [];
    let animationId;
    let width, height;

    function resize() {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
    }

    resize();
    window.addEventListener('resize', resize);

    class Particle {
        constructor() {
            this.reset();
        }

        reset() {
            this.x = Math.random() * width;
            this.y = Math.random() * height;
            this.size = Math.random() * 1.5 + 0.5;
            this.speedX = (Math.random() - 0.5) * 0.3;
            this.speedY = (Math.random() - 0.5) * 0.3;
            this.opacity = Math.random() * 0.4 + 0.1;
            this.color = Math.random() > 0.7
                ? `rgba(232, 122, 46, ${this.opacity})`
                : `rgba(255, 255, 255, ${this.opacity * 0.4})`;
        }

        update() {
            this.x += this.speedX;
            this.y += this.speedY;

            if (this.x < 0 || this.x > width) this.speedX *= -1;
            if (this.y < 0 || this.y > height) this.speedY *= -1;
        }

        draw() {
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fillStyle = this.color;
            ctx.fill();
        }
    }

    // Create particles (fewer for mobile)
    const count = window.innerWidth < 768 ? 30 : 60;
    for (let i = 0; i < count; i++) {
        particles.push(new Particle());
    }

    function connectParticles() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const distance = Math.sqrt(dx * dx + dy * dy);

                if (distance < 120) {
                    const opacity = (1 - distance / 120) * 0.08;
                    ctx.beginPath();
                    ctx.strokeStyle = `rgba(232, 122, 46, ${opacity})`;
                    ctx.lineWidth = 0.5;
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }
        }
    }

    function animate() {
        ctx.clearRect(0, 0, width, height);
        particles.forEach(p => {
            p.update();
            p.draw();
        });
        connectParticles();
        animationId = requestAnimationFrame(animate);
    }

    animate();

    // Reduce particles when tab is hidden
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            cancelAnimationFrame(animationId);
        } else {
            animate();
        }
    });
}

/* ============================================
   CURSOR GLOW EFFECT
   ============================================ */
function initCursorGlow() {
    const glow = document.getElementById('cursorGlow');
    if (!glow || window.innerWidth < 768) return;

    let mouseX = 0, mouseY = 0;
    let currentX = 0, currentY = 0;

    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX;
        mouseY = e.clientY;
    }, { passive: true });

    function updateGlow() {
        currentX += (mouseX - currentX) * 0.08;
        currentY += (mouseY - currentY) * 0.08;

        glow.style.transform = `translate(${currentX - 250}px, ${currentY - 250}px)`;
        requestAnimationFrame(updateGlow);
    }

    updateGlow();
}

/* ============================================
   COUNT UP ANIMATION
   ============================================ */
function initCountUp() {
    const statNumbers = document.querySelectorAll('.stat-number');

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                const target = parseInt(el.getAttribute('data-target'));
                if (!isNaN(target)) {
                    animateCount(el, target);
                }
                observer.unobserve(el);
            }
        });
    }, { threshold: 0.5 });

    statNumbers.forEach(el => observer.observe(el));
}

function animateCount(element, target) {
    const duration = 2000;
    const start = performance.now();
    const startValue = 0;

    function update(currentTime) {
        const elapsed = currentTime - start;
        const progress = Math.min(elapsed / duration, 1);

        // Ease out cubic
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const current = Math.floor(startValue + (target - startValue) * easeOut);

        element.textContent = current.toLocaleString();

        if (progress < 1) {
            requestAnimationFrame(update);
        }
    }

    requestAnimationFrame(update);
}

/* ============================================
   CONTACT FORM — Secure with Validation
   ============================================ */
function initContactForm() {
    const form = document.getElementById('contactForm');
    if (!form) return;

    let lastSubmitTime = 0;
    const RATE_LIMIT_MS = 30000; // 30 seconds between submissions
    const MAX_INPUT_LENGTH = 500;
    const MAX_MESSAGE_LENGTH = 2000;

    // Sanitize text input to prevent XSS
    function sanitize(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // Validate email format
    function isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    // Set button state safely (no user-input in innerHTML)
    function setButtonState(btn, text, disabled, opacity, bg) {
        const span = btn.querySelector('span') || document.createElement('span');
        span.textContent = text;
        if (!btn.contains(span)) {
            btn.innerHTML = '';
            btn.appendChild(span);
        }
        btn.disabled = disabled;
        btn.style.opacity = opacity;
        if (bg) btn.style.background = bg;
    }

    form.addEventListener('submit', (e) => {
        e.preventDefault();

        // Rate limiting
        const now = Date.now();
        if (now - lastSubmitTime < RATE_LIMIT_MS) {
            const waitSec = Math.ceil((RATE_LIMIT_MS - (now - lastSubmitTime)) / 1000);
            alert(`Please wait ${waitSec} seconds before sending another message.`);
            return;
        }

        const btn = form.querySelector('button[type="submit"]');
        const originalHTML = btn.innerHTML;

        // Get and validate inputs
        const name = form.querySelector('#name').value.trim();
        const email = form.querySelector('#email').value.trim();
        const subject = form.querySelector('#subject').value.trim();
        const message = form.querySelector('#message').value.trim();

        if (!name || !email || !message) {
            alert('Please fill in all required fields.');
            return;
        }

        if (name.length > MAX_INPUT_LENGTH || subject.length > MAX_INPUT_LENGTH) {
            alert(`Name and subject must be under ${MAX_INPUT_LENGTH} characters.`);
            return;
        }

        if (message.length > MAX_MESSAGE_LENGTH) {
            alert(`Message must be under ${MAX_MESSAGE_LENGTH} characters.`);
            return;
        }

        if (!isValidEmail(email)) {
            alert('Please enter a valid email address.');
            return;
        }

        // Show sending state
        setButtonState(btn, 'Sending...', true, '0.7', null);
        lastSubmitTime = now;

        // Submit to Formspree (replace YOUR_FORM_ID with actual ID)
        const FORMSPREE_ID = 'YOUR_FORM_ID';

        if (FORMSPREE_ID === 'YOUR_FORM_ID') {
            // Formspree not configured — show demo mode
            setTimeout(() => {
                setButtonState(btn, '✓ Message Sent!', true, '1', 'linear-gradient(135deg, #4caf50, #66bb6a)');
                setTimeout(() => {
                    btn.innerHTML = originalHTML;
                    btn.disabled = false;
                    btn.style.opacity = '1';
                    btn.style.background = '';
                    form.reset();
                }, 3000);
            }, 1500);
            return;
        }

        // Real Formspree submission
        fetch(`https://formspree.io/f/${FORMSPREE_ID}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            body: JSON.stringify({
                name: sanitize(name),
                email: sanitize(email),
                subject: sanitize(subject),
                message: sanitize(message)
            })
        })
        .then(response => {
            if (response.ok) {
                setButtonState(btn, '✓ Message Sent!', true, '1', 'linear-gradient(135deg, #4caf50, #66bb6a)');
                form.reset();
            } else {
                throw new Error('Failed to send');
            }
        })
        .catch(() => {
            setButtonState(btn, '✗ Failed — Try Again', true, '1', 'linear-gradient(135deg, #e53935, #ef5350)');
        })
        .finally(() => {
            setTimeout(() => {
                btn.innerHTML = originalHTML;
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.background = '';
            }, 3000);
        });
    });
}
