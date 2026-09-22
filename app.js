document.addEventListener('DOMContentLoaded', () => {
  const menu = document.querySelector('[data-mobile-menu]');
  document.querySelector('[data-menu-toggle]')?.addEventListener('click', () => menu?.classList.add('is-open'));
  document.querySelector('[data-menu-close]')?.addEventListener('click', () => menu?.classList.remove('is-open'));
  menu?.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => menu.classList.remove('is-open')));
  document.addEventListener('click', (event) => {
    if (menu?.classList.contains('is-open') && !menu.contains(event.target) && !event.target.closest('[data-menu-toggle]')) menu.classList.remove('is-open');
  });

  const loginSlider = document.querySelector('[data-login-slider]');
  if (loginSlider) {
    const slides = [...loginSlider.querySelectorAll('.login-ad-slide')];
    const dots = [...loginSlider.querySelectorAll('[data-login-dot]')];
    let active = 0;
    const show = (index) => {
      if (!slides.length) return;
      active = (index + slides.length) % slides.length;
      slides.forEach((slide, slideIndex) => slide.classList.toggle('is-active', slideIndex === active));
      dots.forEach((dot, dotIndex) => dot.classList.toggle('is-active', dotIndex === active));
    };
    dots.forEach((dot) => dot.addEventListener('click', () => show(Number(dot.dataset.loginDot))));
    show(0);
    if (slides.length > 1) window.setInterval(() => show(active + 1), 5000);
  }
  const slider = document.querySelector('[data-slider]');
  if (slider) {
    const slides = [...slider.querySelectorAll('.hero-slide')];
    const dots = [...slider.querySelectorAll('[data-slide-dot]')];
    let current = 0;
    let timer;
    const showSlide = (index) => {
      current = (index + slides.length) % slides.length;
      slides.forEach((slide, slideIndex) => slide.classList.toggle('is-active', slideIndex === current));
      dots.forEach((dot, dotIndex) => dot.classList.toggle('is-active', dotIndex === current));
      window.clearTimeout(timer);
      const duration = Number(slides[current].dataset.duration) || 5;
      timer = window.setTimeout(() => showSlide(current + 1), duration * 1000);
    };
    slider.querySelector('[data-slide-prev]')?.addEventListener('click', () => showSlide(current - 1));
    slider.querySelector('[data-slide-next]')?.addEventListener('click', () => showSlide(current + 1));
    dots.forEach((dot) => dot.addEventListener('click', () => showSlide(Number(dot.dataset.slideDot))));
    showSlide(0);
  }

  const form = document.querySelector('#sale-form');
  if (form) {
    const total = document.querySelector('#sale-total');
    const inputs = form.querySelectorAll('.quantity-input');
    const updateTotal = () => {
      let sum = 0;
      inputs.forEach((input) => {
        const quantity = Math.max(0, Number(input.value) || 0);
        const price = Number(input.dataset.price) || 0;
        sum += quantity * price;
      });
      total.textContent = `${sum.toLocaleString('ar-IQ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} د.ع`;
    };
    inputs.forEach((input) => input.addEventListener('input', updateTotal));
    updateTotal();
  }

  const quantityInput = document.querySelector('input[name="quantity"][data-price]');
  const reservationTotal = document.querySelector('#reservation-total');
  if (quantityInput && reservationTotal) {
    const updateReservationTotal = () => {
      const quantity = Math.max(1, Number(quantityInput.value) || 1);
      const price = Number(quantityInput.dataset.price) || 0;
      reservationTotal.textContent = `${(quantity * price).toLocaleString('ar-IQ', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} د.ع`;
    };
    quantityInput.addEventListener('input', updateReservationTotal);
    updateReservationTotal();
  }
});
