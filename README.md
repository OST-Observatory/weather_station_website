# OST weather station website
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

You will need the packages python-dev and virtualenv (we assume here a Debian system or one of its derivatives, such as Ubuntu). Moreover you should update pip:

```
sudo apt-get install python-dev-is-python3
pip install -U pip
pip install virtualenv
```

### 2. Create the virtual environment

Create a new virtual python environment and activate it (Bash syntax):

```
virtualenv website_env
source website_env/bin/activate
```

On Windows Computers do

```
virtualenv website_env
website_env\Scripts\Activate
```

If this fails with an error similar to: Error: unsupported locale setting do:

```
export LC_ALL=C
```

If the 'virtualenv' command failed because of an error similar to: 'virtualenv: command not found' add your local bin directory to the path variable. For a bash shell add the following to the .bashrc file in your home directory:

```
export PATH=$PATH:path_to_home/.local/bin
```

Replace 'path_to_home' with the actual path to your home directory.


### 3. Clone the Website from github

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

### 1. Setup the database

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

In .env the secret Django security key, the postgres database password, the server IP and URL, as well as the name of the computer used in production needs to be specified. If a special log directory is required or a different database user was defined during setup, this has to be specified here as well.

```
SECRET_KEY=generate_and_add_your_secret_security_key_here
DATABASE_NAME=weather_station_db
DATABASE_USER=weather_station_user
DATABASE_PASSWORD=your_database_password
DATABASE_HOST=localhost
DATABASE_PORT=
DEVICE=the_name_of_your_device_used_in_production
ALLOWED_HOSTS=server_url,server_ip,localhost
LOG_DIR=logs/
```

Instructions on how to generate a secret key can be found
here: https://tech.serhatteker.com/post/2020-01/django-create-secret-key/

### 3. Setup the database

```
python manage.py makemigrations datasets
python manage.py migrate
```

In case you want a fresh start, run:

```
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc"  -delete
```

and drop the database.

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
          --access-logfile - \
          --workers 3 \
          --timeout 600 \
          --error-logfile /path_to_home_dir/ost_weather/weather_station_website/logs/gunicorn_error.log \
          --capture-output \
          --log-level info \
          --bind unix:/path_to_home_dir/ost_weather/run/gunicorn.sock \
          weather_station.wsgi:application

[Install]
WantedBy=multi-user.target
```

Adjusts the directories and the user name as needed.

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


## Setup logroate

To enable log rotation make a file with the following content in /etc/logrotate.d:

```
/path_to_home_dir/ost_weather/weather_station_website/logs/*.log {
  rotate 14
  daily
  compress
  delaycompress
  nocreate
  notifempty
  missingok
  su weather_station_user www-data
}

```

Change user name, group, and the log directory as needed.

Alternatively, 'logging.handlers.RotatingFileHandler' can be selected as class for the logging handlers in settings_production.py.


## Configure Apache web server

We will deploy the website using the Gunicorn Unix socket defined above on an Apache web server. The Apache reverse proxy functionality will be used for this purpose.

The website should be available on a specific subpage. In our case this is "weather_station". For this to work the variable 'FORCE_SCRIPT_NAME' in 'settings_production.py' is set to '/weather_station'.

### 1. Activate proxy modules

In the first step we will activate the necessary proxy modules.

```
sudo a2enmod proxy
sudo a2enmod proxy_http
```

### 2. Configure the virtual host

The second step is to configure the virtual host. Add the following to your virtual host definition in '/etc/apache2/sites-enabled'.

```
SSLProxyEngine on
SSLProxyVerify none
SSLProxyCheckPeerCN off
SSLProxyCheckPeerName off
ProxyPreserveHost On

ProxyPass /weather_station/static/ !

Define SOCKET_NAME /path_to_home_directory/ost_weather/run/gunicorn.sock
ProxyPass /weather_station unix://${SOCKET_NAME}|http://%{HTTP_HOST}
ProxyPassReverse /weather_station unix://${SOCKET_NAME}|http://%{HTTP_HOST}
```

The first block of lines ensures that our Django weather station app trusts our web server, while the second block ensures that requests for static files are not directed to the Unix socket, as these files are supplied directly by the Apache server (see next step). The third block of commands directs requests to the 'weather_station' page to the Unix socket, and thus to our Django weather app. Replace 'path_to_home_directory' with the actual path to your home directory.


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
The best way to add data is via the API, which can be called via weather_station/weather_api. A good practice is to create an additional user for uploading data.
