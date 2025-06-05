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
