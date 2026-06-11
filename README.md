# OST Weather Station Website
Django website for the OST weather station

## Installing Django and dependencies

In the following we will install the website, Django and all dependencies using a python virtualenv to avoid conflicts with other packages and projects.

### 1. Prerequisites

Create a directory where all files and the required Python modules can be placed:

```
mkdir ost_weather
cd ost_weather
```
For the rest of this guide, we will assume that this directory is located in the user's home directory.

You will need the packages python-dev (we assume here a Debian system or one of its derivatives, such as Ubuntu). Moreover, you should update pip:

```
sudo apt install python-dev-is-python3
pip install -U pip
```

### 2. Create the virtual environment

Create a new virtual python environment and activate it (Bash syntax):

```
python -m venv website_env
source website_env/bin/activate
```

On Windows Computers do

```
python -m venv website_env
website_env\Scripts\Activate
```

If this fails with an error similar to: Error: unsupported locale setting do:

```
export LC_ALL=C
```


### 3. Clone the Website from GitHub

```
git clone https://github.com/OST-Observatory/weather_station_website.git
```

### 4. Install the requirements

```
cd weather_station_website
pip install -r requirements.txt
```


## Running the Website locally

To run the website locally, using the simple sqlite database and the included server:

### 1. Set up the database

```
python manage.py makemigrations datasets
python manage.py migrate
```

In case you want a fresh start, run:

```
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc"  -delete
```

and drop the database or remove the db.sqlite3 file.

### 2. Create a admin user

```
python manage.py createsuperuser
>>> Username: admin_user_name
>>> Email address: admin@example.com
>>> Password: **********
>>> Password (again): *********
>>> Superuser created successfully.
```

### 3. Start the development server

```
python manage.py runserver
```

### API usage (CSV download)

- Last 24h as CSV (streamed): `/weather_api/download-csv/?last_24h=1&dl=csv`
- Custom date range: `/weather_api/download-csv/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&dl=csv`

Notes:
- Responses include `Cache-Control`, `Last-Modified` and `ETag`. Clients may receive `304 Not Modified` when data is unchanged.
- JSON is still available without `dl=csv`.

### Dashboard plot controls

- Quick ranges via preset dropdown or provide a custom time range (start/end date).
- Time resolution is automatically increased when needed to keep plots responsive. A notice is shown on the page if this occurs.
- **Additional plots** (temperature comparison, air quality) load on first click on “Additional Plots” via `/weather_api/additional-plots/` with the same query parameters as the main plot form.
- **Plot cache:** main plots are cached only when time resolution is **≥ 60 s** (finer resolutions, e.g. 1 s for live station tests, are always recomputed). Cached entries use a data fingerprint (`max(added_on)`, `max(pk)`, row count in the JD window) and a short TTL fallback (30 s). Append `?fresh=1` to bypass cache for debugging.
- Cache backend: Django **LocMem** per Gunicorn worker by default. For multiple workers, configure **Redis** as `CACHES` in production settings so plot cache is shared.
- **PostgreSQL plot binning:** for preset/custom ranges **> 1 day** (production PostgreSQL only), plots aggregate in SQL (`percentile_cont`, `SUM`, `AVG` per time bin). Raw rows in the database are unchanged; development SQLite still loads raw points.
- **Bokeh** is served from local static files (`site_static/bokeh/`, version 3.9.1) instead of the pydata CDN.

### Historical data merge (`merge_data_cron.py`)

The cron script downsamples old raw rows (`merged=False`) into binned `merged=True` records and deletes raw rows in the processed window. For live dashboard display, keep the **most recent 1–3 days unmerged** so plots can use full-resolution data. Only merge windows older than that span (tune `days_to_go_back`, `merge_time_span`, and `bin_size` to your retention policy).

## Setup postgres database for production

This is only necessary if you want to run in production.

Install the postgres database:

```
sudo apt install postgresql
```

Start postgres command line:

```
sudo -u postgres psql
```

Create the database, user and connect them:

```
CREATE DATABASE weather_station_db;
CREATE USER weather_station_user WITH PASSWORD 'password';
ALTER ROLE weather_station_user SET client_encoding TO 'utf8';
ALTER ROLE weather_station_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE weather_station_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE weather_station_db TO weather_station_user;
```

List all databases:

```
\l
```

Connect to our database and list all tables:

```
\c weather_station_db
\dt
```

To drop the database and recreate it when you want to completely reset everything (the user does not get deleted in this
process):

```
DROP DATABASE weather_station_db;
CREATE DATABASE weather_station_db;
GRANT ALL PRIVILEGES ON DATABASE weather_station_db TO weather_station_user;
```

Exit the psql:

```
\q
```


## Running the website in production using a postgres database

Instructions modified
from: https://www.digitalocean.com/community/tutorials/how-to-set-up-django-with-postgres-nginx-and-gunicorn-on-ubuntu-18-04

### 1. Create an .env file

To protect secrets like the postgres database password or the Django security key they are embedded in the website via environment variables. The environment variables are defined in the .env file in the weather_station directory. As an example we provide .env.example.

```
cp weather_station/.env.example  weather_station/.env
```

### 2. Adjust the .env file

In .env the secret Django security key, the postgres database password, the server IP and URL, as well as the name of the computer used in production needs to be specified.

```
SECRET_KEY=generate_and_add_your_secret_security_key_here
DATABASE_NAME=weather_station_db
DATABASE_USER=weather_station_user
DATABASE_PASSWORD=your_database_password
DATABASE_HOST=localhost
DATABASE_PORT=
DEVICE=the_name_of_your_device_used_in_production
ALLOWED_HOSTS=server_url,server_ip,localhost
```

Instructions on how to generate a secret key can be found
here: https://tech.serhatteker.com/post/2020-01/django-create-secret-key/

### 3. Set up the database

```
python manage.py migrate
```

### 4. Create a admin user

```
python manage.py createsuperuser
>>> Username: admin_user_name
>>> Email address: admin@example.com
>>> Password: **********
>>> Password (again): *********
>>> Superuser created successfully.
```

You should use a different username instead of admin to increase security.

### 5. Collect static files

```
python manage.py collectstatic
```


## Setup gunicorn

### 1. Create socket unit

```
sudo nano /etc/systemd/system/gunicorn_weather_station.socket
```

Add the following content to this file (adjust the path as needed):

```
[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/path_to_home_dir/ost_weather/run/gunicorn.sock

[Install]
WantedBy=sockets.target
```

Replace 'path_to_home_dir' with the actual home directory.

### 2. Define the service file

```
sudo nano /etc/systemd/system/gunicorn_weather_station.service
```

Add the following content to this file:

```
[Unit]
Description=Weather station gunicorn daemon
Requires=gunicorn_weather_station.socket
After=network.target


[Service]
User=weather_station_user
Group=www-data
WorkingDirectory=/path_to_home_dir/ost_weather/weather_station_website/
ExecStart=/path_to_home_dir/ost_weather/website_env/bin/gunicorn \
          --workers 3 \
          --timeout 600 \
          --access-logfile - \
          --error-logfile - \
          --capture-output \
          --log-level info \
          --bind unix:/path_to_home_dir/ost_weather/run/gunicorn.sock \
          weather_station.wsgi:application

StandardOutput=journal
StandardError=journal
SyslogIdentifier=gunicorn_weather_station


[Install]
WantedBy=multi-user.target
```

Adjusts the directories and the username as needed.

### 3. Start gunicorn and set it up to start at boot

```
sudo systemctl start gunicorn_weather_station.socket
sudo systemctl enable gunicorn_weather_station.socket
```

Check status of gunicorn with and the log files with:

```
sudo systemctl status gunicorn_weather_station.socket
sudo journalctl -u gunicorn_weather_station.socket
```

Check that a gunicorn.sock file is created:

```
ls /path_to_home_dir/www/run/
>>> gunicorn.sock
```

When changes are made to the gunicorn.service file run:

```
sudo systemctl daemon-reload
sudo systemctl restart gunicorn_weather
```

Check status:

```
sudo systemctl status gunicorn_weather
```

## Configure Apache web server

We will deploy the website using the Gunicorn Unix socket defined above on an Apache web server. The Apache reverse proxy functionality will be used for this purpose.

The website should be available on a specific subpage. In our case this is "weather_station". For this to work the variable 'FORCE_SCRIPT_NAME' in 'settings_production.py' is set to '/weather_station'.

### 1. Activate proxy modules

In the first step we will activate the necessary proxy modules.

```
sudo a2enmod proxy
sudo a2enmod proxy_http
sudo a2enmod headers
```

### 2. Configure the virtual host

The second step is to configure the virtual host. Add the following to your virtual host definition in '/etc/apache2/sites-enabled'.

```
SSLProxyEngine on
SSLProxyVerify none
SSLProxyCheckPeerCN off
SSLProxyCheckPeerName off
ProxyPreserveHost On

# Tell Django the client used HTTPS (required for secure cookies / CSRF behind the proxy).
RequestHeader set X-Forwarded-Proto "https" env=HTTPS

ProxyPass /weather_station/static/ !

Define SOCKET_NAME /path_to_home_directory/ost_weather/run/gunicorn.sock
ProxyPass /weather_station unix://${SOCKET_NAME}|http://%{HTTP_HOST}
ProxyPassReverse /weather_station unix://${SOCKET_NAME}|http://%{HTTP_HOST}
```

The first block of lines ensures that our Django weather station app trusts our web server, while the second block ensures that requests for static files are not directed to the Unix socket, as these files are supplied directly by the Apache server (see next step). The third block of commands directs requests to the 'weather_station' page to the Unix socket, and thus to our Django weather app. Replace 'path_to_home_directory' with the actual path to your home directory.

**HTTPS / redirect loops:** Apache terminates TLS; Gunicorn receives plain HTTP. Keep `SECURE_SSL_REDIRECT=False` in `weather_station/.env` (default). If you enable `SECURE_SSL_REDIRECT=True`, Apache must send `X-Forwarded-Proto: https` (see `RequestHeader` above) or the browser will report “The page isn’t redirecting properly”.


### 3. Serve static files

Since Django itself does not serve files, the static files must be served directly from the Apache server. For this purpose, we create a configuration file in "/etc/apache2/conf-available", which we name "weather_station.conf".

Add the following lines to this file:

```
Alias /weather_station/robots.txt /path_to_home_directory/ost_weather/weather_station_website/templates/robots.txt
Alias "/weather_station/static" "/path_to_home_directory/ost_weather/weather_station_website/static"

<Directory /path_to_home_directory/ost_weather/weather_station_website/static>
        Require all granted
</Directory>
```

As always, replace 'path_to_home_directory' with the correct path.

Activate this configuration file with:

```
sudo a2enconf weather_station
```

### 4. Restart the Apache server

Restart the Apache web server so that the changes take into effect:

```
sudo systemctl restart apache2
```

The weather station website should now be up and running.


## Add data

The best way to add data is via the API (`POST /weather_api/datasets/`, HTTP Basic Auth). Create a dedicated Django user for the weather station (not the admin account).

**Production URL:** `https://<host>/weather_station/weather_api/datasets/`  
**Development URL:** `http://127.0.0.1:<port>/weather_api/datasets/` (trailing slash required)

### Upload field semantics (weather station → database)

| Field | Unit / meaning | Notes |
|-------|----------------|-------|
| `jd` | Julian date | Usually set at upload time |
| `temperature`, `sky_temp`, `box_temp` | °C | |
| `pressure` | hPa | 800–1200 |
| `humidity` | % | 0–100 |
| `illuminance` | lx | |
| `wind_speed` | revolutions per sample | Dashboard converts × `0.14` → m/s |
| `rain` | mm in collector | **1.25 mm per gauge tip** × tip count; **not** mm/m² |
| `is_raining` | 0 or 1 | Drop sensor flag |
| `co2_ppm`, `tvoc_ppb` | ppm / ppb | TVOC max 10000 |

**Rain on the dashboard:** stored values are collector depth (mm). Plots sum per time bin, then multiply by `0.07534` (= `10000 / (π×65²)` mm²) to show **mm/m²**. See `datasets/plots.py` (`RAIN_TO_MM_PER_M2_FACTOR`).

Fields `rain_analog` and `baseline` from the Arduino client are ignored by the API.
