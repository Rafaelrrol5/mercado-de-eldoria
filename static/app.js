(() => {
  const catalog = document.querySelector('[data-catalog]');
  if (catalog) {
    const grid = catalog.querySelector('[data-product-grid]');
    const cards = [...catalog.querySelectorAll('[data-product-card]')];
    const controls = {
      search: catalog.querySelector('[data-search]'), category: catalog.querySelector('[data-category]'),
      rarity: catalog.querySelector('[data-rarity]'), className: catalog.querySelector('[data-class]'),
      price: catalog.querySelector('[data-price]'), sort: catalog.querySelector('[data-sort]')
    };
    const apply = () => {
      const term = controls.search.value.trim().toLocaleLowerCase('pt-BR');
      const visible = cards.filter((card) => {
        const categories = card.dataset.category.split('|');
        const matches = (!term || card.dataset.name.includes(term)) &&
          (controls.category.value === 'Todas' || categories.includes(controls.category.value)) &&
          (controls.rarity.value === 'Todas' || card.dataset.rarity === controls.rarity.value) &&
          (controls.className.value === 'Todas' || card.dataset.class === controls.className.value || card.dataset.class === 'Todas') &&
          Number(card.dataset.price) <= Number(controls.price.value);
        card.hidden = !matches;
        return matches;
      });
      const sorters = {
        sold: (a,b) => Number(b.dataset.sales)-Number(a.dataset.sales), low: (a,b) => Number(a.dataset.price)-Number(b.dataset.price),
        high: (a,b) => Number(b.dataset.price)-Number(a.dataset.price), recent: (a,b) => Number(b.dataset.created)-Number(a.dataset.created),
        relevant: (a,b) => Number(b.dataset.offer)-Number(a.dataset.offer) || Number(b.dataset.sales)-Number(a.dataset.sales)
      };
      cards.sort(sorters[controls.sort.value]).forEach((card) => grid.append(card));
      catalog.querySelector('[data-count]').textContent = visible.length;
      catalog.querySelector('[data-empty]').hidden = visible.length !== 0;
      catalog.querySelector('[data-price-label]').textContent = new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL'}).format(Number(controls.price.value)/100);
    };
    Object.values(controls).forEach((control) => control.addEventListener('input', apply));
    catalog.querySelector('[data-clear]').addEventListener('click', () => { controls.search.value=''; controls.category.value='Todas'; controls.rarity.value='Todas'; controls.className.value='Todas'; controls.price.value='3000'; controls.sort.value='relevant'; apply(); });
    apply();
  }
  const supportSelect = document.querySelector('#support-category');
  document.querySelectorAll('[data-support-category]').forEach((button) => button.addEventListener('click', () => {
    if (supportSelect) supportSelect.value = button.dataset.supportCategory;
    document.querySelectorAll('[data-support-category]').forEach((item) => item.classList.toggle('selected', item === button));
    document.querySelector('[data-support-form]')?.scrollIntoView({behavior:'smooth', block:'center'});
  }));
  window.setTimeout(() => document.querySelectorAll('.flash').forEach((item) => item.remove()), 5500);
})();

