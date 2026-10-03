if (document.querySelector('[data-tip]')) {
    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip';
    tooltip.id = 'spending-tooltip';
    tooltip.setAttribute('role', 'tooltip');
    tooltip.hidden = true;
    document.body.append(tooltip);
    let active = null;
    function hide() {
        tooltip.hidden = true;
        active?.removeAttribute('aria-describedby');
        active = null;
    }
    function show(target, event) {
        hide();
        active = target;
        tooltip.textContent = target.dataset.tip;
        tooltip.hidden = false;
        target.setAttribute('aria-describedby', tooltip.id);
        const rect = target.getBoundingClientRect();
        const x = event?.clientX ?? (rect.left + rect.width / 2);
        const y = event?.clientY ?? rect.top;
        const box = tooltip.getBoundingClientRect();
        tooltip.style.left = `${Math.max(12, Math.min(innerWidth - box.width - 12, x - box.width / 2))}px`;
        tooltip.style.top = `${Math.max(12, Math.min(innerHeight - box.height - 12, y - box.height - 16))}px`;
    }
    document.querySelectorAll('[data-tip]').forEach(target => {
        target.addEventListener('pointermove', event => show(target, event));
        target.addEventListener('pointerleave', hide);
        target.addEventListener('focus', () => show(target));
        target.addEventListener('blur', hide);
        target.addEventListener('click', () => show(target));
    });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });
    document.addEventListener('pointerdown', event => { if (!event.target.closest('[data-tip]')) hide(); });
    window.addEventListener('scroll', hide, true);
    window.addEventListener('resize', hide);
}
