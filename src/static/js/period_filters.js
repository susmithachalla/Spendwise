// Keep the native month picker where supported. Some browsers render it as text.
const monthInput = document.getElementById('filter-month');
if (monthInput && monthInput.type !== 'month') {
    const months = ['January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'];
    const canonical = document.createElement('input');
    canonical.type = 'hidden';
    canonical.name = monthInput.name;
    canonical.value = monthInput.value;
    monthInput.removeAttribute('name');
    monthInput.after(canonical);
    monthInput.placeholder = 'October 2026';

    const display = value => {
        if (!value) return '';
        const [year, month] = value.split('-');
        return `${months[Number(month) - 1]} ${year}`;
    };
    monthInput.value = display(canonical.value);
    monthInput.defaultValue = monthInput.value;

    const sync = () => {
        const value = monthInput.value.trim();
        const match = /^([a-z]+)\s+([0-9]{4})$/i.exec(value);
        const index = match ? months.findIndex(month => month.toLowerCase() === match[1].toLowerCase()) : -1;
        const valid = !value || (index >= 0 && Number(match[2]) > 0);
        monthInput.setCustomValidity(valid ? '' : 'Enter a month and year, such as October 2026.');
        canonical.value = valid && value ? `${match[2]}-${String(index + 1).padStart(2, '0')}` : '';
    };
    monthInput.addEventListener('input', sync);
    monthInput.addEventListener('change', () => {
        sync();
        if (monthInput.validity.valid) monthInput.value = display(canonical.value);
    });
    monthInput.form.addEventListener('reset', () => setTimeout(sync, 0));
}
