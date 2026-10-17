(() => {
  const regions = () => [...document.querySelectorAll('[data-live-region]')];
  if (!regions().length || !window.fetch) return;
  let running = false, stopped = false;
  let badge = document.querySelector('[data-live-status]');
  if (!badge) {
    badge = document.createElement('p'); badge.dataset.liveStatus = '';
    badge.className = 'form-help'; badge.setAttribute('role','status');
    const main = document.querySelector('main'); main.prepend(badge);
  }
  badge.textContent = 'Atualização automática a cada 5 segundos.';
  document.addEventListener('input', event => {
    const form = event.target.closest('form');
    if (form) form.dataset.editing = 'true';
  });
  async function refresh() {
    if (running || stopped || document.hidden) return;
    running = true;
    try {
      const response = await fetch(window.location.href.split('#')[0], {
        credentials:'same-origin', cache:'no-store', headers:{'X-Live-Refresh':'1'}
      });
      if (response.redirected || response.status === 401 || response.status === 403 || response.status === 404) {
        stopped = true;
        badge.textContent = 'Sessão encerrada. Entre novamente para continuar.';
        regions().forEach(region => { region.replaceChildren(document.createTextNode('Entre novamente para visualizar os dados.')); });
        return;
      }
      if (!response.ok || !response.headers.get('content-type')?.includes('text/html')) throw new Error('refresh');
      const next = new DOMParser().parseFromString(await response.text(), 'text/html');
      const incoming = [...next.querySelectorAll('[data-live-region]')];
      if (!incoming.length) throw new Error('refresh');
      regions().forEach(region => {
        const source = incoming.find(item => item.dataset.liveRegion === region.dataset.liveRegion);
        if (!source || region.querySelector('form[data-editing=true]')) return;
        if (region.innerHTML === source.innerHTML) return;
        const expanded = [...region.querySelectorAll('details')].map(item => item.open);
        const scrolls = [...region.querySelectorAll('.admin-table,.finance-chart')].map(item => [item.scrollLeft,item.scrollTop]);
        region.replaceChildren(...[...source.childNodes].map(node => document.importNode(node,true)));
        region.querySelectorAll('details').forEach((item,index) => { item.open = !!expanded[index]; });
        region.querySelectorAll('.admin-table,.finance-chart').forEach((item,index) => {
          if (scrolls[index]) { item.scrollLeft=scrolls[index][0]; item.scrollTop=scrolls[index][1]; }
        });
      });
      badge.textContent = 'Sincronizado às ' + new Intl.DateTimeFormat('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'}).format(new Date()) + ' · a cada 5 s';
    } catch {
      badge.textContent = 'Sem conexão com o servidor. Tentando reconectar…';
    } finally { running=false; }
  }
  window.setInterval(refresh,5000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  window.addEventListener('online',refresh);
})();
