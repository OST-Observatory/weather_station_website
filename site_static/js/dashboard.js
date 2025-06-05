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
});

function downloadCSV(data, filename) {
    // Convert data to CSV format
    const headers = ['JD', 'Temperature (°C)', 'Pressure (hPa)', 'Humidity (g/m³)', 
                    'Illuminance (lx)', 'Wind Speed (m/s)', 'Rain', 'Note', 
                    'Merged', 'Added On', 'Last Modified'];
    const csvContent = [
        headers.join(','),
        ...data.map(row => [
            row.jd,
            row.temperature,
            row.pressure,
            row.humidity,
            row.illuminance,
            row.wind_speed,
            row.rain,
            row.note,
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
    // Convert FormData to URL parameters
    const params = new URLSearchParams(formData);
    const url = `/weather_api/download-csv/?${params.toString()}`;

    // Clear previous error messages
    const errorDiv = document.getElementById('form-error');
    errorDiv.style.display = 'none';
    errorDiv.textContent = '';

    fetch(url, {
        method: 'GET',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Accept': 'application/json'
        }
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.errors ? JSON.stringify(data.errors) : data.message || 'An error occurred');
            });
        }
        return response.json();
    })
    .then(data => {
        if (data.status === 'success') {
            downloadCSV(data.data, 'weather_data.csv');
        } else {
            throw new Error(data.message || 'An error occurred');
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
        
        // Display error in the form
        errorDiv.textContent = errorMessage;
        errorDiv.style.display = 'block';
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
