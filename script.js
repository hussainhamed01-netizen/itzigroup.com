/* ============================================
   ITZIGROUP — TECH FOR FUTURE
   Main JavaScript — Interactions & Effects

   Shared by the home page and the ItziPDF pages. Every module checks
   that its elements exist, so the script is safe to include on any page.
   Animations respect the visitor's "reduce motion" setting.
   ============================================ */

(function () {
    'use strict';

    const reducedMotionQuery = window.matchMedia
        ? window.matchMedia('(prefers-reduced-motion: reduce)')
        : null;

    function prefersReducedMotion() {
        return Boolean(reducedMotionQuery && reducedMotionQuery.matches);
    }

    function onReducedMotionChange(callback) {
        if (!reducedMotionQuery) return;
        if (typeof reducedMotionQuery.addEventListener === 'function') {
            reducedMotionQuery.addEventListener('change', callback);
        } else if (typeof reducedMotionQuery.addListener === 'function') {
            reducedMotionQuery.addListener(callback);
        }
    }

    function init() {
        // One failing module must not stop the others
        [
            initNavbar,
            initMobileNav,
            initSmoothScroll,
            initScrollReveal,
            initParticles,
            initCursorGlow,
            initCountUp,
            initActiveNavHighlight,
            initScreenshotGallery
        ].forEach((module) => {
            try {
                module();
            } catch (error) {
                if (window.console) console.error(error);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    /* ============================================
       NAVBAR — Scroll Effect
       ============================================ */
    function initNavbar() {
        const navbar = document.getElementById('navbar');
        if (!navbar) return;

        let ticking = false;

        function update() {
            navbar.classList.toggle('scrolled', window.pageYOffset > 50);
            ticking = false;
        }

        window.addEventListener('scroll', () => {
            if (!ticking) {
                ticking = true;
                window.requestAnimationFrame(update);
            }
        }, { passive: true });

        // Correct state when the page is opened already scrolled (reload, anchor link)
        update();
    }

    /* ============================================
       MOBILE NAVIGATION
       ============================================ */
    function initMobileNav() {
        const toggle = document.getElementById('navToggle');
        const navLinks = document.getElementById('navLinks');
        if (!toggle || !navLinks) return;

        const openLabel = toggle.getAttribute('data-label-open') || 'Open menu';
        const closeLabel = toggle.getAttribute('data-label-close') || 'Close menu';

        if (!toggle.hasAttribute('aria-controls')) {
            toggle.setAttribute('aria-controls', 'navLinks');
        }

        function setOpen(open) {
            toggle.classList.toggle('active', open);
            navLinks.classList.toggle('active', open);
            toggle.setAttribute('aria-expanded', String(open));
            toggle.setAttribute('aria-label', open ? closeLabel : openLabel);
            document.body.style.overflow = open ? 'hidden' : '';
        }

        function isOpen() {
            return navLinks.classList.contains('active');
        }

        setOpen(false);

        toggle.addEventListener('click', () => {
            setOpen(!isOpen());
        });

        // Close menu when clicking a link
        navLinks.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', () => setOpen(false));
        });

        // Close with Escape and return focus to the toggle
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && isOpen()) {
                setOpen(false);
                toggle.focus();
            }
        });

        // Close when the layout switches back to the desktop navigation
        window.addEventListener('resize', () => {
            if (isOpen() && window.innerWidth > 900) setOpen(false);
        }, { passive: true });
    }

    /* ============================================
       SMOOTH SCROLL (in-page anchors)
       ============================================ */
    function initSmoothScroll() {
        document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
            anchor.addEventListener('click', (event) => {
                const hash = anchor.getAttribute('href');
                if (!hash || hash.length < 2) return;

                let id;
                try {
                    id = decodeURIComponent(hash.slice(1));
                } catch (error) {
                    return;
                }

                const target = document.getElementById(id);
                if (!target) return;

                event.preventDefault();
                target.scrollIntoView({
                    behavior: prefersReducedMotion() ? 'auto' : 'smooth',
                    block: 'start'
                });

                // Keep the address bar and history in sync, like a normal anchor
                if (window.history && typeof window.history.pushState === 'function' && window.location.hash !== hash) {
                    window.history.pushState(null, '', hash);
                }

                // Move keyboard focus to the target (skip link, in-page navigation)
                if (!target.hasAttribute('tabindex') && !/^(A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY)$/.test(target.tagName)) {
                    target.setAttribute('tabindex', '-1');
                }
                target.focus({ preventScroll: true });
            });
        });
    }

    /* ============================================
       SCROLL REVEAL (Custom AOS)
       ============================================ */
    function initScrollReveal() {
        const elements = document.querySelectorAll('[data-aos]');
        if (!elements.length) return;

        function revealAll() {
            elements.forEach((el) => el.classList.add('aos-animate'));
        }

        if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
            revealAll();
            return;
        }

        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    const delay = parseInt(entry.target.getAttribute('data-aos-delay'), 10) || 0;
                    setTimeout(() => {
                        entry.target.classList.add('aos-animate');
                    }, delay);
                    observer.unobserve(entry.target);
                }
            });
        }, {
            threshold: 0.1,
            rootMargin: '0px 0px -50px 0px'
        });

        elements.forEach((el) => observer.observe(el));

        onReducedMotionChange(() => {
            if (prefersReducedMotion()) {
                observer.disconnect();
                revealAll();
            }
        });
    }

    /* ============================================
       ACTIVE NAV HIGHLIGHT
       ============================================ */
    function initActiveNavHighlight() {
        const navLinks = Array.from(document.querySelectorAll('.nav-link'))
            .filter((link) => (link.getAttribute('href') || '').charAt(0) === '#');
        if (!navLinks.length || !('IntersectionObserver' in window)) return;

        const sections = Array.from(document.querySelectorAll('section[id]'))
            .filter((section) => navLinks.some((link) => link.getAttribute('href') === `#${section.id}`));
        if (!sections.length) return;

        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    const id = entry.target.getAttribute('id');
                    navLinks.forEach((link) => {
                        const isCurrent = link.getAttribute('href') === `#${id}`;
                        link.classList.toggle('active', isCurrent);
                        if (isCurrent) {
                            link.setAttribute('aria-current', 'location');
                        } else {
                            link.removeAttribute('aria-current');
                        }
                    });
                }
            });
        }, {
            threshold: 0.3,
            rootMargin: '-80px 0px -50% 0px'
        });

        sections.forEach((section) => observer.observe(section));
    }

    /* ============================================
       PARTICLE SYSTEM
       ============================================ */
    function initParticles() {
        const canvas = document.getElementById('particleCanvas');
        if (!canvas || typeof canvas.getContext !== 'function') return;

        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const particles = [];
        let animationId = null;
        let width = 0;
        let height = 0;
        let resizeTimer = null;

        function resize() {
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight;
        }

        resize();
        window.addEventListener('resize', () => {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                resize();
                if (animationId === null) drawFrame();
            }, 150);
        }, { passive: true });

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

        function drawFrame() {
            ctx.clearRect(0, 0, width, height);
            particles.forEach((p) => p.draw());
            connectParticles();
        }

        function animate() {
            ctx.clearRect(0, 0, width, height);
            particles.forEach((p) => {
                p.update();
                p.draw();
            });
            connectParticles();
            animationId = requestAnimationFrame(animate);
        }

        function start() {
            if (animationId !== null || document.hidden || prefersReducedMotion()) return;
            animationId = requestAnimationFrame(animate);
        }

        function stop() {
            if (animationId !== null) cancelAnimationFrame(animationId);
            animationId = null;
        }

        // Reduced motion: a single still frame instead of a moving field
        if (prefersReducedMotion()) {
            drawFrame();
        } else {
            start();
        }

        // Pause while the tab is hidden
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                stop();
            } else {
                start();
            }
        });

        onReducedMotionChange(() => {
            if (prefersReducedMotion()) {
                stop();
                drawFrame();
            } else {
                start();
            }
        });
    }

    /* ============================================
       CURSOR GLOW EFFECT
       ============================================ */
    function initCursorGlow() {
        const glow = document.getElementById('cursorGlow');
        if (!glow || window.innerWidth < 768 || prefersReducedMotion()) return;
        if (window.matchMedia && !window.matchMedia('(pointer: fine)').matches) return;

        let mouseX = 0, mouseY = 0;
        let currentX = 0, currentY = 0;
        let frame = null;

        function updateGlow() {
            currentX += (mouseX - currentX) * 0.08;
            currentY += (mouseY - currentY) * 0.08;

            glow.style.transform = `translate(${currentX - 250}px, ${currentY - 250}px)`;

            // Stop the loop once the glow has caught up with the pointer
            if (Math.abs(mouseX - currentX) < 0.5 && Math.abs(mouseY - currentY) < 0.5) {
                frame = null;
                return;
            }
            frame = requestAnimationFrame(updateGlow);
        }

        document.addEventListener('mousemove', (e) => {
            mouseX = e.clientX;
            mouseY = e.clientY;
            if (frame === null && !prefersReducedMotion()) {
                frame = requestAnimationFrame(updateGlow);
            }
        }, { passive: true });
    }

    /* ============================================
       COUNT UP ANIMATION
       ============================================ */
    function initCountUp() {
        const statNumbers = Array.from(document.querySelectorAll('.stat-number'))
            .filter((el) => !isNaN(parseInt(el.getAttribute('data-target'), 10)));
        if (!statNumbers.length) return;

        if (prefersReducedMotion() || !('IntersectionObserver' in window)) {
            statNumbers.forEach((el) => {
                el.textContent = parseInt(el.getAttribute('data-target'), 10).toLocaleString();
            });
            return;
        }

        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    const el = entry.target;
                    animateCount(el, parseInt(el.getAttribute('data-target'), 10));
                    observer.unobserve(el);
                }
            });
        }, { threshold: 0.5 });

        statNumbers.forEach((el) => observer.observe(el));
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
       SCREENSHOT GALLERY (ItziPDF pages)
       ============================================ */
    function initScreenshotGallery() {
        const switcher = document.querySelector('.gallery-switcher');
        if (!switcher) return;

        const galleryTabs = Array.from(switcher.querySelectorAll('.gallery-language-tab'));
        const galleryPanels = Array.from(switcher.querySelectorAll('.gallery-panel'));
        const galleryHint = switcher.querySelector('.gallery-hint');
        const prevBtn = switcher.querySelector('[data-gallery-scroll="prev"]');
        const nextBtn = switcher.querySelector('[data-gallery-scroll="next"]');

        function activeRail() {
            const openPanel = galleryPanels.find((panel) => !panel.hidden);
            return openPanel ? openPanel.querySelector('.screenshot-rail') : null;
        }

        function activateGalleryTab(activeTab) {
            galleryTabs.forEach((tab) => {
                const isActive = tab === activeTab;
                tab.setAttribute('aria-selected', String(isActive));
                tab.tabIndex = isActive ? 0 : -1;
            });

            galleryPanels.forEach((panel) => {
                panel.hidden = panel.id !== activeTab.dataset.galleryPanel;
            });

            if (galleryHint) {
                const isArabic = activeTab.dataset.galleryLang === 'ar';
                const nextText = isArabic ? galleryHint.dataset.arabic : galleryHint.dataset.english;
                if (nextText) galleryHint.textContent = nextText;
                galleryHint.lang = isArabic ? 'ar' : 'en';
                galleryHint.dir = isArabic ? 'rtl' : 'ltr';
            }
        }

        galleryTabs.forEach((tab, index) => {
            tab.addEventListener('click', () => activateGalleryTab(tab));
            tab.addEventListener('keydown', (event) => {
                if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
                event.preventDefault();
                let nextTab;
                if (event.key === 'Home') {
                    nextTab = galleryTabs[0];
                } else if (event.key === 'End') {
                    nextTab = galleryTabs[galleryTabs.length - 1];
                } else {
                    const isRtl = document.documentElement.dir === 'rtl';
                    const step = event.key === 'ArrowRight' ? (isRtl ? -1 : 1) : (isRtl ? 1 : -1);
                    nextTab = galleryTabs[(index + step + galleryTabs.length) % galleryTabs.length];
                }
                activateGalleryTab(nextTab);
                nextTab.focus();
            });
        });

        function scrollRail(direction) {
            const rail = activeRail();
            if (!rail) return;
            const card = rail.querySelector('.screenshot-card');
            const delta = card ? card.getBoundingClientRect().width + 20 : 280;
            const panelRtl = getComputedStyle(rail).direction === 'rtl';
            const signed = direction * (panelRtl ? -1 : 1) * delta;
            rail.scrollBy({
                left: signed,
                behavior: prefersReducedMotion() ? 'auto' : 'smooth'
            });
        }

        prevBtn?.addEventListener('click', () => scrollRail(-1));
        nextBtn?.addEventListener('click', () => scrollRail(1));
    }
})();
