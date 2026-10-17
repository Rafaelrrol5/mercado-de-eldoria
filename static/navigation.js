(() => {
  const news = document.querySelector('.game-updates');
  if (news) news.closest('section').id = 'novidades';
  const panel = document.querySelector('#realm-navigation');
  if (!panel) return;
  const triggers = [...document.querySelectorAll('[data-navigation]')];
  const tabs = [...panel.querySelectorAll('[role=tab]')];
  const backdrop = document.querySelector('.mega-backdrop');
  let activeTrigger;
  function select(tab, focus = false) {
    tabs.forEach(item => {
      const selected = item === tab;
      item.setAttribute('aria-selected', String(selected));
      item.tabIndex = selected ? 0 : -1;
      document.getElementById(item.getAttribute('aria-controls')).hidden = !selected;
    });
    if (focus) tab.focus();
  }
  function close(restore = false) {
    panel.hidden = backdrop.hidden = true;
    triggers.forEach(button => button.setAttribute('aria-expanded', 'false'));
    if (restore) activeTrigger?.focus();
  }
  triggers.forEach(button => button.addEventListener('click', () => {
    if (button.getAttribute('aria-expanded') === 'true') { close(); return; }
    activeTrigger = button;
    const group = button.dataset.navigation;
    triggers.forEach(item => item.setAttribute('aria-expanded', String(item === button)));
    tabs.forEach(tab => { tab.hidden = tab.dataset.navGroup !== group; });
    select(tabs.find(tab => !tab.hidden));
    panel.hidden = backdrop.hidden = false;
    const mobile = document.querySelector('.mobile-menu');
    if (mobile) mobile.open = false;
  }));
  tabs.forEach(tab => {
    tab.addEventListener('click', () => select(tab));
    tab.addEventListener('keydown', event => {
      const visible = tabs.filter(item => !item.hidden);
      let index = visible.indexOf(tab);
      if (['ArrowDown', 'ArrowRight'].includes(event.key)) index = (index + 1) % visible.length;
      else if (['ArrowUp', 'ArrowLeft'].includes(event.key)) index = (index - 1 + visible.length) % visible.length;
      else if (event.key === 'Home') index = 0;
      else if (event.key === 'End') index = visible.length - 1;
      else return;
      event.preventDefault(); select(visible[index], true);
    });
  });
  panel.querySelector('.mega-close').addEventListener('click', () => close(true));
  backdrop.addEventListener('click', () => close());
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) close(true); });
  document.addEventListener('focusin', event => { if (!panel.hidden && !event.target.closest('.site-header')) close(); });
})();
