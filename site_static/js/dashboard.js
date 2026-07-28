
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function setHidden(el, hidden) {
    if (!el) {
        return;
    }
    el.hidden = hidden;
    // Legacy CSS class .not_vissible { display: none } must be toggled;
    // clearing inline style alone is not enough (unlike jQuery .show()).
    el.classList.toggle('not_vissible', hidden);
    if (hidden) {
        el.style.display = 'none';
    } else {
        el.style.display = '';
    }
}

function isVisible(el) {
    return Boolean(el)
        && !el.hidden
        && el.style.display !== 'none'
        && !el.classList.contains('not_vissible');
}

document.addEventListener('DOMContentLoaded', function () {
    const weatherForm = document.getElementById('weather-data-form');
    const downloadForm = document.getElementById('download-data-form');
    const formsContainer = document.querySelector('.forms-container');
    const showPlotOptions = document.getElementById('show-plot-options');
    const showDownloadOptions = document.getElementById('show-download-options');
    const showAdditionalPlots = document.getElementById('show-additional-plots');

    setHidden(weatherForm, true);
    setHidden(downloadForm, true);
    setHidden(formsContainer, true);

    function showForm(formToShow) {
        setHidden(weatherForm, true);
        setHidden(downloadForm, true);
        const target = document.querySelector(formToShow);
        setHidden(target, false);
        setHidden(formsContainer, false);

        document.querySelectorAll('.toggle-button').forEach((btn) => {
            btn.classList.remove('active');
        });
        if (formToShow === '#weather-data-form' && showPlotOptions) {
            showPlotOptions.classList.add('active');
        } else if (showDownloadOptions) {
            showDownloadOptions.classList.add('active');
        }
    }

    function hideAllForms() {
        setHidden(weatherForm, true);
        setHidden(downloadForm, true);
        setHidden(formsContainer, true);
        document.querySelectorAll('.toggle-button').forEach((btn) => {
            btn.classList.remove('active');
        });
    }

    if (showPlotOptions) {
        showPlotOptions.addEventListener('click', function () {
            if (isVisible(weatherForm)) {
                hideAllForms();
            } else {
                showForm('#weather-data-form');
            }
        });
    }

    if (showDownloadOptions) {
        showDownloadOptions.addEventListener('click', function () {
            if (isVisible(downloadForm)) {
                hideAllForms();
            } else {
                showForm('#download-data-form');
            }
        });
    }

    const ADDITIONAL_PLOT_TITLES = {
        temp_combined: 'Temperatures (Ambient / Sky / Box)',
        temp_sky_diff: 'Temperature Difference (Ambient - Sky)',
        uv_index: 'UV Index',
        air_quality: 'Particulate Matter (PM1.0 / PM2.5 / PM10)',
    };
    const ADDITIONAL_PLOT_ORDER = [
        'temp_combined',
        'temp_sky_diff',
        'uv_index',
        'air_quality',
    ];

    function appendBokehScript(scriptPayload) {
        if (!scriptPayload) {
            return;
        }
        const nonce = window.CSP_NONCE || '';
        requestAnimationFrame(() => {
            // Prefer raw JS from components(..., wrap_script=False).
            // Fall back to extracting <script> tags if a wrapped string is cached.
            const trimmed = String(scriptPayload).trim();
            if (trimmed.startsWith('<')) {
                const wrapper = document.createElement('div');
                wrapper.innerHTML = scriptPayload;
                Array.from(wrapper.querySelectorAll('script')).forEach((node) => {
                    const script = document.createElement('script');
                    if (nonce) {
                        script.setAttribute('nonce', nonce);
                    }
                    if (node.src) {
                        script.src = node.src;
                    } else {
                        script.textContent = node.textContent;
                    }
                    document.body.appendChild(script);
                });
                return;
            }
            const script = document.createElement('script');
            if (nonce) {
                script.setAttribute('nonce', nonce);
            }
            script.textContent = scriptPayload;
            document.body.appendChild(script);
        });
    }

    function setTextMessage(container, message, className) {
        container.replaceChildren();
        const el = document.createElement('div');
        el.className = className;
        el.textContent = message;
        container.appendChild(el);
    }

    function insertTrustedHtml(parent, html) {
        const template = document.createElement('template');
        template.innerHTML = html;
        parent.appendChild(template.content.cloneNode(true));
    }

    function buildAdditionalPlotsFragment(figures) {
        const fragment = document.createDocumentFragment();
        const plotKeys = [
            ...ADDITIONAL_PLOT_ORDER,
            ...Object.keys(figures).filter(
                (key) => key !== 'note' && !ADDITIONAL_PLOT_ORDER.includes(key)
            ),
        ];

        let hasContent = false;
        plotKeys.forEach((key) => {
            const plotHtml = figures[key];
            if (!plotHtml) {
                return;
            }
            hasContent = true;
            const title = ADDITIONAL_PLOT_TITLES[key] || key.replace(/_/g, ' ');
            const heading = document.createElement('h2');
            heading.className = 'weather-data__heading';
            heading.textContent = title;
            fragment.appendChild(heading);

            const figureWrap = document.createElement('div');
            figureWrap.className = 'weather-data-figure';
            insertTrustedHtml(figureWrap, plotHtml);
            fragment.appendChild(figureWrap);
        });

        if (figures.note) {
            hasContent = true;
            const note = document.createElement('div');
            note.className = 'weather-data-form muted-hint plot-data-warning';
            note.textContent = String(figures.note);
            fragment.appendChild(note);
        }

        if (!hasContent) {
            const empty = document.createElement('div');
            empty.className = 'additional-plots-placeholder muted-hint';
            empty.textContent = 'No additional plot data for the selected range.';
            fragment.appendChild(empty);
        }
        return fragment;
    }

    function plotQueryParams() {
        const source = new URLSearchParams(window.location.search);
        const allowed = ['plot_range', 'time_resolution', 'start_date', 'end_date', 'fresh'];
        const params = new URLSearchParams();
        let hasRange = false;

        allowed.forEach((key) => {
            const value = source.get(key);
            if (value !== null && String(value).trim() !== '') {
                params.set(key, value);
                if (key === 'plot_range' || key === 'start_date') {
                    hasRange = true;
                }
            }
        });

        if (!hasRange && window.PLOT_QUERY_DEFAULTS) {
            Object.entries(window.PLOT_QUERY_DEFAULTS).forEach(([key, value]) => {
                if (
                    value !== null
                    && String(value).trim() !== ''
                    && !params.has(key)
                ) {
                    params.set(key, value);
                }
            });
        }

        return params;
    }

    function loadAdditionalPlots() {
        const container = document.getElementById('additional-plots');
        const content = document.getElementById('additional-plots-content');
        if (!content) {
            return Promise.resolve();
        }
        const params = plotQueryParams();

        setTextMessage(
            content,
            'Loading additional plots…',
            'additional-plots-placeholder muted-hint'
        );

        return fetch(`${window.ADDITIONAL_PLOTS_URL}?${params.toString()}`)
            .then(async (response) => {
                if (!response.ok) {
                    let message = `Failed to load additional plots (${response.status})`;
                    try {
                        const data = await response.json();
                        if (data.detail) {
                            message = String(data.detail);
                        } else if (data.code) {
                            message = String(data.code);
                        } else if (data.errors) {
                            message = 'Invalid plot parameters';
                        }
                    } catch (e) {
                        // ignore non-JSON error bodies
                    }
                    throw new Error(message);
                }
                return response.json();
            })
            .then((data) => {
                content.replaceChildren();
                content.appendChild(buildAdditionalPlotsFragment(data.figures || {}));
                appendBokehScript(data.script);
                if (container) {
                    container.setAttribute('data-loaded', 'true');
                }
                setTimeout(function () {
                    window.dispatchEvent(new Event('resize'));
                }, 0);
            })
            .catch((error) => {
                setTextMessage(
                    content,
                    error.message || 'Failed to load additional plots.',
                    'weather-data-form muted-hint plot-data-warning'
                );
            });
    }

    const ADDITIONAL_PLOTS_OPEN_KEY = 'additionalPlotsOpen';

    function setAdditionalPlotsOpen(isOpen) {
        try {
            sessionStorage.setItem(ADDITIONAL_PLOTS_OPEN_KEY, isOpen ? '1' : '0');
        } catch (e) {
            // ignore storage failures
        }
    }

    function wasAdditionalPlotsOpen() {
        try {
            return sessionStorage.getItem(ADDITIONAL_PLOTS_OPEN_KEY) === '1';
        } catch (e) {
            return false;
        }
    }

    function expandAdditionalPlots() {
        const container = document.getElementById('additional-plots');
        if (!container) {
            return Promise.resolve();
        }
        container.classList.remove('collapsed');
        if (showAdditionalPlots) {
            showAdditionalPlots.classList.add('active');
        }
        setAdditionalPlotsOpen(true);
        if (container.getAttribute('data-loaded') !== 'true') {
            return loadAdditionalPlots();
        }
        setTimeout(function () {
            window.dispatchEvent(new Event('resize'));
        }, 0);
        return Promise.resolve();
    }

    if (showAdditionalPlots) {
        showAdditionalPlots.addEventListener('click', function () {
            const container = document.getElementById('additional-plots');
            if (!container) {
                return;
            }
            const makeVisible = container.classList.contains('collapsed');
            if (makeVisible) {
                expandAdditionalPlots();
            } else {
                container.classList.add('collapsed');
                showAdditionalPlots.classList.remove('active');
                setAdditionalPlotsOpen(false);
            }
        });
    }

    if (wasAdditionalPlotsOpen()) {
        expandAdditionalPlots();
    }

    const plotNotice = document.getElementById('plot-notice');
    if (plotNotice) {
        const hidePlotNotice = () => plotNotice.classList.add('plot-notice-hidden');
        const dismissBtn = plotNotice.querySelector('.plot-notice-dismiss');
        if (dismissBtn) {
            dismissBtn.addEventListener('click', hidePlotNotice);
        }
        setTimeout(hidePlotNotice, 8000);
    }

    try {
        const ts = parseInt(localStorage.getItem('justRefreshedTs') || '0', 10);
        if (ts && (Date.now() - ts) < 10000) {
            const toast = document.createElement('div');
            toast.className = 'auto-refresh-toast';
            toast.textContent = 'Updated just now';
            document.body.appendChild(toast);
            setTimeout(() => {
                if (toast && toast.parentNode) toast.parentNode.removeChild(toast);
            }, 3000);
        }
        localStorage.removeItem('justRefreshedTs');
    } catch (e) {
        // ignore
    }

    document.querySelectorAll('form[data-csv-download]').forEach((form) => {
        form.addEventListener('submit', function (event) {
            event.preventDefault();
            handleCSVDownload(new FormData(form));
        });
    });
});

function downloadCSV(data, filename) {
    const headers = [
        'ID', 'JD', 'Temperature (°C)', 'Sky Temperature (°C)', 'Box Temperature (°C)',
        'Pressure (hPa)', 'Humidity [%]', 'Illuminance (lx)', 'Wind Speed (m/s)',
        'Rain', 'Is Raining (0/1)', 'PM1.0 (ug/m3)', 'PM2.5 (ug/m3)', 'PM10 (ug/m3)', 'UV Index',
        'Note', 'Merged', 'Added On', 'Last Modified'
    ];

    const csvContent = [
        headers.join(','),
        ...data.map(row => [
            row.pk,
            row.jd,
            row.temperature,
            row.sky_temp,
            row.box_temp,
            row.pressure,
            row.humidity,
            row.illuminance,
            row.wind_speed,
            row.rain,
            row.is_raining,
            row.pm1_0,
            row.pm2_5,
            row.pm10,
            row.uv_index,
            (row.note || '').toString().replace(/\n|\r|,/g, ' '),
            row.merged,
            row.added_on,
            row.last_modified
        ].join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    if (navigator.msSaveBlob) {
        navigator.msSaveBlob(blob, filename);
    } else {
        link.href = URL.createObjectURL(blob);
        link.setAttribute('download', filename);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

function handleCSVDownload(formData) {
    if (formData.has('csrfmiddlewaretoken')) {
        formData.delete('csrfmiddlewaretoken');
    }
    const params = new URLSearchParams(formData);
    params.set('dl', 'csv');
    const url = `${window.API_URL}?${params.toString()}`;

    const errorDiv = document.getElementById('form-error');
    if (errorDiv) {
        errorDiv.hidden = true;
        errorDiv.textContent = '';
    }

    fetch(url, {
        method: 'GET'
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.errors ? JSON.stringify(data.errors) : data.message || 'An error occurred');
            });
        }
        const contentType = response.headers.get('Content-Type') || '';
        if (contentType.includes('text/csv')) {
            return response.blob().then(blob => ({ blob, isCSV: true }));
        }
        return response.json().then(data => ({ data, isCSV: false }));
    })
    .then(result => {
        if (result.isCSV) {
            const blob = result.blob;
            const link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.setAttribute('download', 'weather_data.csv');
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            return;
        }
        const data = result.data;
        if (data && data.status === 'success') {
            downloadCSV(data.data, 'weather_data.csv');
        } else {
            throw new Error((data && data.message) || 'An error occurred');
        }
    })
    .catch(error => {
        let errorMessage = 'An error occurred';
        try {
            const errorData = JSON.parse(error.message);
            if (typeof errorData === 'object') {
                const errorMessages = [];
                for (const [field, messages] of Object.entries(errorData)) {
                    if (field === '__all__') {
                        errorMessages.push(messages.join(', '));
                    } else {
                        errorMessages.push(`${field}: ${messages.join(', ')}`);
                    }
                }
                errorMessage = errorMessages.join('\n');
            } else {
                errorMessage = errorData;
            }
        } catch (e) {
            errorMessage = error.message;
        }
        if (errorDiv) {
            errorDiv.textContent = errorMessage;
            errorDiv.hidden = false;
        }
    });
}

(function () {
    const AUTO_REFRESH_MIN_MS = 30 * 60 * 1000;

    function shouldAutoRefresh() {
        try {
            const url = new URL(window.location.href);
            const hasCustom = url.searchParams.has('start_date') && url.searchParams.has('end_date');
            if (hasCustom) return false;

            const last = parseInt(localStorage.getItem('lastAutoRefreshTs') || '0', 10);
            const now = Date.now();
            if (Number.isFinite(last) && now - last < AUTO_REFRESH_MIN_MS) return false;
            localStorage.setItem('lastAutoRefreshTs', String(now));
            return true;
        } catch (_) {
            return true;
        }
    }

    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && shouldAutoRefresh()) {
            try { localStorage.setItem('justRefreshedTs', String(Date.now())); } catch (_) {}
            window.location.reload();
        }
    });
})();
