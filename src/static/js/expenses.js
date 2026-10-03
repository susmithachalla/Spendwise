// Enhance the server-rendered options; the original select still submits currency.
const currencySelect = document.getElementById('currency');
if (currencySelect) {
    const updateCurrencyHint = () => {
        const option = currencySelect.selectedOptions[0];
        const code = currencySelect.value;
        const digits = Number(option.dataset.digits);
        document.getElementById('amount-code').textContent = code ? `(${code})` : '';
        document.getElementById('amount-help').textContent = code
            ? `${code}: ${digits === 0 ? 'whole amounts only' : `up to ${digits} decimal places`}. Use a decimal point without commas. No conversion or rounding.`
            : 'Choose a currency, then enter the amount.';
        document.getElementById('amount').placeholder = digits === 0 ? 'e.g. 125' : `e.g. 125.${'5'.padEnd(digits, '0')}`;
    };
    currencySelect.addEventListener('change', updateCurrencyHint);
    updateCurrencyHint();
    enhanceCurrencySelect(currencySelect);
}

function enhanceCurrencySelect(select) {
    const popular = ['INR', 'USD', 'EUR', 'GBP', 'CAD', 'AUD', 'AED', 'SGD'];
    const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().trim();
    const currencies = Array.from(select.options).filter(option => option.value).map(option => ({
        code: option.value,
        label: option.textContent.trim(),
        search: normalize(`${option.textContent} ${option.dataset.countries || ''}`),
    }));
    const wrapper = document.createElement('div');
    wrapper.className = 'currency-picker';
    wrapper.innerHTML = `
        <button type="button" class="form-input currency-trigger" id="currency-trigger"
            aria-haspopup="dialog" aria-expanded="false" aria-controls="currency-popup"
            aria-labelledby="currency-label currency-value" aria-describedby="currency-help">
            <span id="currency-value"></span><span class="currency-chevron" aria-hidden="true"></span>
        </button>
        <div class="currency-popup" id="currency-popup" role="dialog" aria-label="Choose a currency" hidden>
            <div class="currency-search-area">
                <label class="currency-sr-only" for="currency-search">Search currencies by code, country, name, or symbol</label>
                <input type="text" id="currency-search" class="form-input currency-search"
                    role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="currency-results"
                    autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="Search code, country, name, symbol…">
            </div>
            <div id="currency-results" class="currency-results" role="listbox" aria-label="Currencies"></div>
            <p class="currency-empty" hidden>No currencies found. Try another code, country, or symbol.</p>
            <p class="currency-sr-only" role="status" aria-live="polite" aria-atomic="true"></p>
        </div>`;
    select.after(wrapper);
    const trigger = wrapper.querySelector('.currency-trigger');
    const value = wrapper.querySelector('#currency-value');
    const popup = wrapper.querySelector('.currency-popup');
    const search = wrapper.querySelector('.currency-search');
    const results = wrapper.querySelector('.currency-results');
    const empty = wrapper.querySelector('.currency-empty');
    const status = wrapper.querySelector('[role="status"]');
    let options = [];
    let active = -1;

    function syncSelection() {
        value.textContent = select.selectedOptions[0]?.textContent.trim() || 'Choose a currency';
        trigger.setAttribute('aria-invalid', String(!select.value));
    }

    function activate(index, scroll = true) {
        active = options.length ? Math.max(0, Math.min(index, options.length - 1)) : -1;
        options.forEach((option, i) => {
            option.classList.toggle('is-active', i === active);
            option.setAttribute('aria-selected', String(i === active));
        });
        if (active < 0) {
            search.removeAttribute('aria-activedescendant');
            return;
        }
        const option = options[active];
        search.setAttribute('aria-activedescendant', option.id);
        if (scroll) {
            // Scroll only the list, never the document behind it.
            const top = option.offsetTop;
            const bottom = top + option.offsetHeight;
            if (top < results.scrollTop) results.scrollTop = top;
            else if (bottom > results.scrollTop + results.clientHeight) results.scrollTop = bottom - results.clientHeight;
        }
    }

    function render() {
        const query = normalize(search.value);
        const matches = currencies.filter(item => query.split(/\s+/).every(word => item.search.includes(word)));
        results.replaceChildren();
        options = [];
        const groups = query ? [['Search results', matches]] : [
            ['Popular currencies', popular.map(code => currencies.find(item => item.code === code)).filter(Boolean)],
            ['All currencies', currencies],
        ];
        groups.forEach(([title, items], groupIndex) => {
            if (!items.length) return;
            const group = document.createElement('div');
            group.setAttribute('role', 'group');
            const heading = document.createElement('div');
            heading.id = `currency-group-${groupIndex}`;
            heading.className = 'currency-group-title';
            heading.textContent = title;
            group.setAttribute('aria-labelledby', heading.id);
            group.append(heading);
            items.forEach(item => {
                const option = document.createElement('div');
                option.id = `currency-option-${options.length}`;
                option.className = 'currency-option';
                option.setAttribute('role', 'option');
                option.dataset.code = item.code;
                option.textContent = item.label;
                if (item.code === select.value) option.classList.add('is-current');
                option.addEventListener('click', () => choose(item.code));
                options.push(option);
                group.append(option);
            });
            results.append(group);
        });
        empty.hidden = matches.length > 0;
        status.textContent = `${matches.length} ${matches.length === 1 ? 'currency' : 'currencies'} available.`;
        results.scrollTop = 0;
        activate(query ? 0 : Math.max(0, options.findIndex(option => option.dataset.code === select.value)), false);
    }

    function positionPopup() {
        if (popup.hidden) return;
        const rect = trigger.getBoundingClientRect();
        const viewport = window.visualViewport;
        const top = viewport?.offsetTop || 0;
        const bottom = top + (viewport?.height || window.innerHeight);
        const below = bottom - rect.bottom - 12;
        const above = rect.top - top - 12;
        const upwards = below < 240 && above > below;
        wrapper.classList.toggle('opens-up', upwards);
        popup.style.maxHeight = `${Math.max(0, Math.min(320, upwards ? above : below))}px`;
    }

    function open() {
        if (!popup.hidden) return;
        popup.hidden = false;
        trigger.setAttribute('aria-expanded', 'true');
        search.setAttribute('aria-expanded', 'true');
        search.value = '';
        render();
        positionPopup();
        search.focus({ preventScroll: true });
        activate(active);
    }

    function close(restoreFocus = false) {
        popup.hidden = true;
        trigger.setAttribute('aria-expanded', 'false');
        search.setAttribute('aria-expanded', 'false');
        search.removeAttribute('aria-activedescendant');
        if (restoreFocus) trigger.focus({ preventScroll: true });
    }

    function choose(code) {
        select.value = code;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        close(true);
    }

    trigger.addEventListener('click', () => popup.hidden ? open() : close(true));
    trigger.addEventListener('keydown', event => {
        if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
            event.preventDefault();
            open();
        } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey && event.key !== ' ') {
            event.preventDefault();
            open();
            search.value = event.key;
            render();
        }
    });
    search.addEventListener('input', render);
    search.addEventListener('keydown', event => {
        if (event.isComposing) return;
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            activate(active + (event.key === 'ArrowDown' ? 1 : -1));
        } else if (event.key === 'Enter') {
            event.preventDefault(); // Search must never submit the expense form.
            if (active >= 0) choose(options[active].dataset.code);
        } else if (event.key === 'Tab') {
            // Return focus to the trigger before the browser advances naturally.
            close(true);
        }
    });
    wrapper.addEventListener('keydown', event => {
        if (event.key === 'Escape' && !popup.hidden) {
            event.preventDefault();
            event.stopPropagation();
            close(true);
        }
    });
    wrapper.addEventListener('focusout', event => {
        if (!wrapper.contains(event.relatedTarget)) close();
    });
    // Keep combobox focus while choosing with a mouse (touch scrolling stays native).
    results.addEventListener('mousedown', event => event.preventDefault());
    document.addEventListener('pointerdown', event => {
        if (!wrapper.contains(event.target)) close();
    });
    window.addEventListener('resize', positionPopup);
    window.addEventListener('scroll', positionPopup, true);
    window.visualViewport?.addEventListener('resize', positionPopup);
    window.visualViewport?.addEventListener('scroll', positionPopup);
    select.addEventListener('change', syncSelection);
    select.addEventListener('invalid', event => {
        event.preventDefault();
        trigger.setAttribute('aria-invalid', 'true');
        open();
        status.textContent = 'Please choose a currency.';
    });
    select.form?.addEventListener('reset', () => setTimeout(() => {
        select.dispatchEvent(new Event('change', { bubbles: true }));
        close();
    }, 0));
    syncSelection();
    // Hide only after enhancement succeeds; keep the select enabled for submission.
    select.hidden = true;
    document.getElementById('currency-label').htmlFor = trigger.id;
}

const categorySelect = document.getElementById('category');
if (categorySelect) {
    const updateCategoryHelp = () => {
        const icon = document.getElementById('selected-category-icon');
        icon.hidden = !categorySelect.value;
        icon.querySelector('path').setAttribute('d', categorySelect.selectedOptions[0]?.dataset.icon || '');
        document.getElementById('category-help').textContent =
            categorySelect.selectedOptions[0]?.dataset.description || 'Choose the best match for this expense.';
    };
    categorySelect.addEventListener('change', updateCategoryHelp);
    categorySelect.form?.addEventListener('reset', () => setTimeout(updateCategoryHelp, 0));
    updateCategoryHelp();
}
