(() => {
  const menu = document.querySelector('.mobile-menu');
  document.addEventListener('click', event => {
    if (menu?.open && (!menu.contains(event.target) || event.target.closest('a'))) menu.open = false;
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu?.open) { menu.open = false; menu.querySelector('summary').focus(); }
  });
  if ('IntersectionObserver' in window && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const observer = new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) { entry.target.classList.add('reveal-ready'); observer.unobserve(entry.target); }
    }), { threshold: .1 });
    document.querySelectorAll('.realm-card, .feature-grid > article, .game-features > article, .update').forEach(element => observer.observe(element));
  }
})();
