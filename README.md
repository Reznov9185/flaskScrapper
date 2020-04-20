#### YouTube API-V3 Scrapper

###### How it works!

1. Authenticate google Account's via `OAuth2.0` 
2. Fetches `Youtube` channel `videos`
3. Fetches `Video` statistics
4. Store the data in a `database`
5. Tries to find `videos` performances (just a dummy)
6. `Sort` by performances(views) & `filter`(by tags)

###### How to run:
Clone this `repository` then,
Run the following commands for `python-3` on `unix` based systems (I am using `venv` as well),

    sudo apt update
    sudo apt install python3-pip
    pip install -r requirements.txt
    export FLASK_APP=app.py
    
Also, make sure now that you have `mysql` database running locally,
create a database and update connection string on the `mysql` setting on `database.py`, line `5`. For example,
    
    mysql://{username}:{password}@{host}/{database_name} 

Now for background task I have used `celery`, so on terminal,

    celery -A app.celery worker

Finally on terminal,

    flask run
    
You should see a server running here, `http://127.0.0.1:5000/`

#### Goals
##### Learning Pointers
1. [Flask](https://flask.palletsprojects.com/en/1.1.x/) as a micro-framework
2. [Youtube API3](https://developers.google.com/youtube/v3)
3. [SQLAlchemy & it's ORM](https://www.sqlalchemy.org/) for `database` comms
4. [Celery](http://www.celeryproject.org/) as `async` task manager


##### TODO
1. Refactor the `directory` structure, follow the correct `design pattern`
2. Further `test` coverage
3. More robust `database` design
4. Efficient `database` connection handling
5. Migration options with `package` like, `Flask-Migrate`
5. Better error handling

###### Notes:
* App runs on `http` locally, so might have to advanced through couple of security warnings!
