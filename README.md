# OST weather station website
Django website for the OST weather station

## Installing Django and dependencies

In the following we will install the website, Django and all dependencies using a python virtualenv to avoid conflicts with other packages and projects.

### 1. Prerequisites

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

Start postgres command line:

```
sudo -u postgres psql
```

Create the database, user and connect them:

```
CREATE DATABASE weatherstationdb;
CREATE USER weatherstationuser WITH PASSWORD 'password';
ALTER ROLE weatherstationuser SET client_encoding TO 'utf8';
ALTER ROLE weatherstationuser SET default_transaction_isolation TO 'read committed';
ALTER ROLE weatherstationuser SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE weatherstationdb TO weatherstationuser;
```

List all databases:

```
\l
```

Connect to our database and list all tables:

```
\c weatherstationdb
\dt
```

To drop the database and recreate it when you want to completely reset everything (the user does not get deleted in this
process):

```
DROP DATABASE weatherstationdb;
CREATE DATABASE weatherstationdb;
GRANT ALL PRIVILEGES ON DATABASE weatherstationdb TO weatherstationuser;
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
DATABASE_NAME=weatherstationdb
DATABASE_USER=weatherstationuser
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
sudo nano /etc/systemd/system/gunicorn_weather.socket
```

Add the following content to this file (adjust the path as needed):

```
[Unit]
Description=gunicorn socket

[Socket]
ListenStream=/path_to_home_dir/www/run/gunicorn.sock

[Install]
WantedBy=sockets.target
```

Replace 'path_to_home_dir' with the actual Home directory.

### 2. Define the service file

```
sudo nano /etc/systemd/system/gunicorn_weather.service
```

Add the following content to this file:

```
[Unit]
Description=Weather station gunicorn daemon
Requires=gunicorn_weather.socket
After=network.target


[Service]
User=weather_station_user
Group=www-data
WorkingDirectory=/path_to_home_dir/www/weather_station_website/
ExecStart=/path_to_home_dir/www/website_env/bin/gunicorn \
          --access-logfile - \
          --workers 3 \
          --timeout 600 \
          --error-logfile /path_to_home_dir/www/weather_station_website/logs/gunicorn_error.log \
          --capture-output \
          --log-level info \
          --bind unix:/path_to_home_dir/www/run/gunicorn.sock \
          weather_station.wsgi:application

[Install]
WantedBy=multi-user.target
```

Adjusts the directories and the user name as needed.

### 3. Start gunicorn and set it up to start at boot

```
sudo systemctl start gunicorn_weather.socket
sudo systemctl enable gunicorn_weather.socket
```

Check status of gunicorn with and the log files with:

```
sudo systemctl status gunicorn_weather.socket
sudo journalctl -u gunicorn_weather.socket
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

To enable log rotation the following file should be added to /etc/logrotate.d:

```
/path_to_home_dir/www/weather_station_website/logs/django.log {
  rotate 14
  daily
  compress
  delaycompress
  nocreate
  notifempty
  missingok
  su weather_station_user www-data
}
/path_to_home_dir/www/weather_station_website/logs/not_django.log {
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


## Configure APACHE2

