(() => {
  document.querySelectorAll('[data-password-toggle]').forEach(button => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.getAttribute('aria-controls'));
      const visible = input.type === 'password';
      input.type = visible ? 'text' : 'password';
      button.title = visible ? 'Ocultar senha' : 'Mostrar senha';
      button.setAttribute('aria-pressed', String(visible));
      button.setAttribute('aria-label', (visible ? 'Ocultar ' : 'Mostrar ') + (document.querySelector(`label[for="${input.id}"]`)?.textContent || 'senha'));
    });
  });
  document.querySelectorAll('[data-auth-form]').forEach(form => {
    form.querySelectorAll('input:not([type=hidden])').forEach(input => {
      const check = () => {
        input.setCustomValidity('');
        if (input.hasAttribute('data-new-password')) {
          const valid = input.value.length >= 8 && input.value.length <= 128 && /\p{L}/u.test(input.value) && /\p{N}/u.test(input.value);
          const rules = document.querySelector(`[data-password-rules="${input.id}"]`);
          if (rules) rules.dataset.valid = String(valid);
          if (input.value && !valid) input.setCustomValidity('Use de 8 a 128 caracteres, incluindo letras e números.');
        }
        if (input.name === 'confirmation' && input.value !== form.elements.password?.value) input.setCustomValidity('As senhas precisam ser iguais.');
        input.setAttribute('aria-invalid', String(!input.validity.valid));
        const message = input.closest('.field')?.querySelector('[data-field-message]');
        if (message) message.textContent = input.validationMessage;
      };
      input.addEventListener('blur', check);
      input.addEventListener('input', () => {
        check();
        if (input.name === 'password' && form.elements.confirmation) form.elements.confirmation.setCustomValidity('');
      });
    });
  });
})();
