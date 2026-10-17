(() => {
  const cart = document.querySelector('[data-live-cart]');
  const forms = [...(cart?.querySelectorAll('form') || [])];
  if (!forms.length || !window.fetch) return;
  const status = cart.querySelector('[data-cart-status]');
  const checkout = cart.querySelector('[data-cart-checkout]');
  const currency = new Intl.NumberFormat('pt-BR', {style:'currency', currency:'BRL'});
  let revision = 0, saved = 0, timer, pending;
  function preview() {
    let total = 0, valid = true;
    forms.forEach(form => {
      const input = form.elements.quantity;
      if (!input.checkValidity()) { valid = false; return; }
      const line = form.closest('[data-cart-line]');
      const amount = Number(line.dataset.price) * Number(input.value);
      line.querySelector('[data-line-total]').textContent = currency.format(amount / 100);
      total += amount;
    });
    if (valid) cart.querySelectorAll('[data-cart-total]').forEach(item => item.textContent = currency.format(total / 100));
    checkout.setAttribute('aria-disabled', String(!valid || total === 0));
    return valid;
  }
  async function save() {
    clearTimeout(timer);
    if (pending) return pending;
    pending = (async () => {
      while (saved < revision) {
        if (!preview()) { status.textContent = 'Informe quantidades inteiras entre 1 e 20.'; return false; }
        const current = revision;
        const data = new FormData();
        data.set('csrf_token', forms[0].elements.csrf_token.value);
        forms.forEach(form => { data.append('slug', form.elements.slug.value); data.append('quantity', form.elements.quantity.value); });
        status.textContent = 'Salvando bolsa…';
        try {
          const response = await fetch(forms[0].action, {method:'POST', body:data, headers:{'X-Cart-Update':'1'}, credentials:'same-origin'});
          if (!response.ok) throw new Error('save');
          const result = await response.json();
          saved = current;
          const bag = document.querySelector('.bag-link');
          if (bag) {
            bag.setAttribute('aria-label', `Bolsa do Aventureiro com ${result.count} itens`);
            let badge = bag.querySelector('span');
            if (!badge) { badge = document.createElement('span'); bag.append(badge); }
            badge.textContent = result.count; badge.hidden = result.count === 0;
          }
        } catch {
          status.textContent = 'Não foi possível salvar. Altere a quantidade ou clique em Ir para o checkout para tentar novamente.';
          return false;
        }
      }
      status.textContent = 'Bolsa atualizada.';
      return true;
    })();
    try { return await pending; } finally { pending = null; }
  }
  forms.forEach(form => {
    form.elements.quantity.addEventListener('input', () => {
      const input = form.elements.quantity;
      if (input.value !== '' && Number(input.value) < 1) input.value = '1';
      revision++; preview(); clearTimeout(timer);
      status.textContent = 'Alterações pendentes…';
      timer = setTimeout(save, 300);
    });
    form.addEventListener('submit', event => { event.preventDefault(); save(); });
  });
  checkout.addEventListener('click', async event => {
    event.preventDefault();
    if (!preview() || checkout.getAttribute('aria-disabled') === 'true') return;
    if (await save()) window.location.assign(checkout.href);
  });
})();
