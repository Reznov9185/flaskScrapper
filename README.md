#### Flask Scrapper

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

##### Learning Pointers
1. Flask
2. Youtube API3
3. SQLAlchemy & it's ORM
4. Celery


##### TODO
1. Refactor the `directory` structure
2. Test coverage
3. More robust `database` design
4. Efficient `database` connection handling
5. Migration options with `package` like, `Flask-Migrate`
5. Better error handling
