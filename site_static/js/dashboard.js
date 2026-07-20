// Function to get CSRF token from cookies
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

$(document).ready(function () {
    // Hide both forms initially
    $('#weather-data-form').hide();
    $('#download-data-form').hide();
    $('.forms-container').hide();

    // Function to show a form and hide the other
    function showForm(formToShow) {
        $('#weather-data-form, #download-data-form').hide();
        $(formToShow).show();
        $('.forms-container').show();
        
        // Update button states
        $('.toggle-button').removeClass('active');
        if (formToShow === '#weather-data-form') {
            $('#show-plot-options').addClass('active');
        } else {
            $('#show-download-options').addClass('active');
        }
    }

    // Function to hide all forms
    function hideAllForms() {
        $('#weather-data-form, #download-data-form, .forms-container').hide();
        $('.toggle-button').removeClass('active');
    }

    // Toggle plot options
    $('#show-plot-options').on("click", function () {
        if ($('#weather-data-form').is(':visible')) {
            hideAllForms();
        } else {
            showForm('#weather-data-form');
        }
    });

    // Toggle download options
    $('#show-download-options').on("click", function () {
        if ($('#download-data-form').is(':visible')) {
            hideAllForms();
        } else {
            showForm('#download-data-form');
        }
    });

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

    function appendBokehScript(scriptHtml) {
        if (!scriptHtml) {
            return;
        }
        // Defer until plot container divs are in the DOM (Bokeh 3.x embed is async).
        requestAnimationFrame(() => {
            const wrapper = document.createElement('div');
            wrapper.innerHTML = scriptHtml;
            Array.from(wrapper.querySelectorAll('script')).forEach((node) => {
                const script = document.createElement('script');
                if (node.src) {
                    script.src = node.src;
                } else {
                    script.textContent = node.textContent;
                }
                document.body.appendChild(script);
            });
        });
    }

    function buildAdditionalPlotsHtml(figures) {
        const sections = [];
        const plotKeys = [
            ...ADDITIONAL_PLOT_ORDER,
            ...Object.keys(figures).filter(
                (key) => key !== 'note' && !ADDITIONAL_PLOT_ORDER.includes(key)
            ),
        ];

        plotKeys.forEach((key) => {
            const plotHtml = figures[key];
            if (!plotHtml) {
                return;
            }
            const title = ADDITIONAL_PLOT_TITLES[key] || key.replace(/_/g, ' ');
            sections.push(
                `<h2 class="weather-data__heading">${title}</h2>`,
                '<div class="weather-data-figure">',
                plotHtml,
                '</div>'
            );
        });

        if (figures.note) {
            sections.push(
                '<div class="weather-data-form muted-hint plot-data-warning">',
                figures.note,
                '</div>'
            );
        }
        if (!sections.length) {
            return '<div class="additional-plots-placeholder muted-hint">No additional plot data for the selected range.</div>';
        }
        return sections.join('');
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
        const $container = $('#additional-plots');
        const $content = $('#additional-plots-content');
        const params = plotQueryParams();

        $content.html('<div class="additional-plots-placeholder muted-hint">Loading additional plots…</div>');

        return fetch(`${window.ADDITIONAL_PLOTS_URL}?${params.toString()}`)
            .then(async (response) => {
                if (!response.ok) {
                    let message = `Failed to load additional plots (${response.status})`;
                    try {
                        const data = await response.json();
                        message = data.errors
                            ? JSON.stringify(data.errors)
                            : (data.detail || message);
                    } catch (e) {
                        // ignore non-JSON error bodies
                    }
                    throw new Error(message);
                }
                return response.json();
            })
            .then((data) => {
                $content.html(buildAdditionalPlotsHtml(data.figures || {}));
                appendBokehScript(data.script);
                $container.attr('data-loaded', 'true');
                setTimeout(function () {
                    window.dispatchEvent(new Event('resize'));
                }, 0);
            })
            .catch((error) => {
                $content.html(
                    `<div class="weather-data-form muted-hint plot-data-warning">${error.message || 'Failed to load additional plots.'}</div>`
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
        const $container = $('#additional-plots');
        $container.removeClass('collapsed');
        $('#show-additional-plots').addClass('active');
        setAdditionalPlotsOpen(true);
        if ($container.attr('data-loaded') !== 'true') {
            return loadAdditionalPlots();
        }
        setTimeout(function () {
            window.dispatchEvent(new Event('resize'));
        }, 0);
        return Promise.resolve();
    }

    // Toggle additional plots (lazy load on first expand)
    $('#show-additional-plots').on("click", function () {
        const $container = $('#additional-plots');
        const makeVisible = $container.hasClass('collapsed');
        if (makeVisible) {
            expandAdditionalPlots();
        } else {
            $container.addClass('collapsed');
            $('#show-additional-plots').removeClass('active');
            setAdditionalPlotsOpen(false);
        }
    });

    // Restore additional plots after auto-refresh / reload if they were open
    if (wasAdditionalPlotsOpen()) {
        expandAdditionalPlots();
    }

    // Auto-hide plot resolution notice (dismissible toast)
    const plotNotice = document.getElementById('plot-notice');
    if (plotNotice) {
        const hidePlotNotice = () => plotNotice.classList.add('plot-notice-hidden');
        const dismissBtn = plotNotice.querySelector('.plot-notice-dismiss');
        if (dismissBtn) {
            dismissBtn.addEventListener('click', hidePlotNotice);
        }
        setTimeout(hidePlotNotice, 8000);
    }

    // Show auto-refresh toast if we just reloaded programmatically
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
});

function downloadCSV(data, filename) {
    // Convert data to CSV format (include all fields)
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
    // Remove CSRF token from GET request params (not needed and clutters URL)
    if (formData.has('csrfmiddlewaretoken')) {
        formData.delete('csrfmiddlewaretoken');
    }
    // Convert FormData to URL parameters
    const params = new URLSearchParams(formData);
    // Request server-side CSV streaming by default (dl=csv)
    params.set('dl', 'csv');
    const url = `${window.API_URL}?${params.toString()}`;

    // Clear previous error messages
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
            // Try to parse JSON error for form validation feedback
            return response.json().then(data => {
                throw new Error(data.errors ? JSON.stringify(data.errors) : data.message || 'An error occurred');
            });
        }
        const contentType = response.headers.get('Content-Type') || '';
        if (contentType.includes('text/csv')) {
            return response.blob().then(blob => ({ blob, isCSV: true }));
        }
        // Fallback: JSON response (legacy)
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
            // Legacy path: build CSV on client if server returned JSON
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
                // Handle form validation errors
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

function handleDownload(form) {
    const formData = new FormData(form);
    const queryString = new URLSearchParams(formData).toString();
    
    fetch(`/weather_api/download-csv/?${queryString}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                downloadCSV(data.data, 'weather_data.csv');
            } else {
                // Display errors in the form
                const errorDiv = form.querySelector('.error');
                if (errorDiv) {
                    errorDiv.textContent = data.message || 'An error occurred';
                }
            }
        })
        .catch(error => {
            console.error('Error:', error);
            const errorDiv = form.querySelector('.error');
            if (errorDiv) {
                errorDiv.textContent = 'An error occurred while downloading the data';
            }
        });
    
    return false; // Prevent form submission
}

// -------- Auto refresh on tab focus (without forcing for custom time ranges) --------
(function () {
    const AUTO_REFRESH_MIN_MS = 30 * 60 * 1000; // 30 minutes cooldown

    function shouldAutoRefresh() {
        try {
            const url = new URL(window.location.href);
            const hasCustom = url.searchParams.has('start_date') && url.searchParams.has('end_date');
            if (hasCustom) return false; // Don't refresh when explicit custom range selected

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
