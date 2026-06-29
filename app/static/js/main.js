document.addEventListener('DOMContentLoaded', () => {

  const allCheckIn  = document.querySelectorAll('[name="ngay_nhan"]');
  const allCheckOut = document.querySelectorAll('[name="ngay_tra"]');

  allCheckIn.forEach(inEl => {
    inEl.addEventListener('change', () => {
      allCheckOut.forEach(outEl => {
        outEl.min = inEl.value;
        if (outEl.value && outEl.value <= inEl.value) {
          outEl.value = '';
          showToast('Ngày trả phòng phải sau ngày nhận phòng.', 'info');
        }
      });
    });
  });

  const today = new Date().toISOString().split('T')[0];
  document.querySelectorAll('input[type="date"]').forEach(el => {
    if (!el.min) el.min = today;
  });

  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => el.remove(), 5000);
  });

  const heroForm    = document.getElementById('hero-search-form');
  const filterForm  = document.getElementById('filter-form');

  if (heroForm && filterForm) {
    ['ngay_nhan', 'ngay_tra'].forEach(name => {
      const heroInput   = heroForm.querySelector(`[name="${name}"]`);
      const filterInput = filterForm.querySelector(`[name="${name}"]`);
      if (heroInput && filterInput) {
        heroInput.addEventListener('change', () => { filterInput.value = heroInput.value; });
        filterInput.addEventListener('change', () => { heroInput.value = filterInput.value; });
      }
    });
  }

  window.showToast = function(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `flash flash--${type}`;
    toast.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;min-width:280px;max-width:380px;';
    toast.innerHTML = `<span>${message}</span><button class="flash-close" onclick="this.parentElement.remove()">✕</button>`;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
  };

  document.querySelectorAll('a[href*="/bookings/new"]').forEach(link => {
    link.addEventListener('click', e => {
      const loggedIn = document.body.dataset.loggedIn === 'true';
      if (!loggedIn) {
        e.preventDefault();
        const target = link.getAttribute('href');
        if (confirm('Bạn cần đăng nhập để đặt phòng. Chuyển đến trang đăng nhập?')) {
          window.location.href = `/login?next=${encodeURIComponent(target)}`;
        }
      }
    });
  });

});
