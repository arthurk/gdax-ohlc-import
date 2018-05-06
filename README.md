gdax-ohlc-import
================

This is a script that fetches all historical OHLC data from GDAX.

The data has a 1-minute interval and can be used to carry out further in-depth analysis of market trends. All traded products (BTC, BCH, ETH, LTC) will be imported into a local SQLite database. The import will begin from the earliest trading date (see below). The script can be invoked periodically (for example with a cronjob) to fetch the latest data. It will automatically resume from the latest saved date.

- [gdax-ohlc-import](#gdax-ohlc-import)
  * [Starting Dates](#starting-dates)
- [Installation](#installation)
  * [virtualenv (pipenv)](#virtualenv--pipenv-)
  * [Docker](#docker)
- [Usage](#usage)
- [Data Format](#data-format)
  * [Export to CSV](#export-to-csv)
  * [Import to Pandas](#import-to-pandas)

API rate limits are respected (currently the limit is 3 req/s, the script will do 1 req/s). It will also re-try fetching and continue to the next symbol after 3 failed attempts.

Starting Dates
--------------

    # Bitcoin 
    BTC-EUR: 2015-04-23 | BTC-USD: 2015-01-08 | BTC-GBP: 2015-04-21

    # Ethereum
    ETH-BTC: 2016-05-18 | ETH-EUR: 2017-05-23 | ETH-USD: 2016-05-18

    # Litecoin
    LTC-BTC: 2016-08-17 | LTC-USD: 2016-08-17 | LTC-EUR: 2017-05-22
    
    # Bitcoin Cash
    BCH-BTC: 2018-01-17 | BCH-USD: 2017-12-20 | BCH-EUR: 2018-01-24

Installation
============

virtualenv (pipenv)
-------------------

The script has been tested with Python 3.5 and 3.6.

You need the `sqlite3` library installed on your system. On macOS you can use homebrew: `brew install sqlite3`.

To install the development environment, clone the repo and run:

    $ pipenv install

Docker
------

You can build the Docker image with:

    $ docker build -t gdax .

Usage
=====

    ➤ pipenv run python main.py --help
    usage: main.py [-h] [-l LOGLEVEL] [-s START_DATE] [-p PRODUCT] db_file

    GDAX Fetcher

    positional arguments:
      db_file               sqlite3 db file path

    optional arguments:
      -h, --help            show this help message and exit
      -l LOGLEVEL, --loglevel LOGLEVEL
                            Loglevel. DEBUG|INFO|WARNING|ERROR|CRITICAL
      -s START_DATE, --start-date START_DATE
                            Process candles since given date. YYYY-mm-dd format
      -p PRODUCT, --product PRODUCT
                            Which product to update

You can run the script with the following command:

    $ pipenv run python main.py db.sqlite3

Or if you prefer Docker:

    $ docker run --rm gdax python main.py db.sqlite3

This will start fetching data into the `db.sqlite3` file. If it's the first run it will start from the earliest trading day. You can abort the script at any time and it will resume fetching from the last saved state. 

    2018-05-06 20:37:07,173 INFO     Updating ['BCH-BTC', 'BCH-USD', 'BCH-EUR', 'BTC-EUR', 'BTC-USD', 'BTC-GBP', 'ETH-BTC', 'ETH-EUR', 'ETH-USD', 'LTC-BTC', 'LTC-USD', 'LTC-EUR']
    2018-05-06 20:37:07,175 INFO     No previous data found. Importing full history
    2018-05-06 20:37:07,175 INFO     1/12 | BCH-BTC | starting from 2018-01-17 00:00:00
    2018-05-06 20:37:12,996 INFO     BCH-BTC | importing 2018-01-18
    2018-05-06 20:37:19,931 INFO     BCH-BTC | importing 2018-01-19
    2018-05-06 20:37:25,257 INFO     BCH-BTC | importing 2018-01-20

If you don't want to fetch all history for every product you can use the `--start-date` and `--product` flags. For example this will fetch the OHLC data for ETH-USD starting from March 2018:

    $ pipenv run python main.py -p ETH-USD -s 2018-03-01 debug_db.sqlite3

    2018-05-06 20:45:00,656 INFO     Updating ['ETH-USD']
    2018-05-06 20:45:00,660 INFO     1/1 | ETH-USD | starting from 2018-03-01 00:00:00

Data Format
===========

The data will be stored in an SQLite3 database table called `candles`. It has the following structure:

    market
    time
    open
    high
    low
    close
    volume

You can use the `sqlite3` cli to inspect the data::

    $ sqlite3 gdax.sqlite3
    sqlite> SELECT * FROM candles;
    BCH-BTC|1516400040|0.15418|0.15418|0.15418|0.15418|0.25917758
    BCH-BTC|1516399920|0.15375|0.15375|0.15375|0.15375|0.0539563
    BCH-BTC|1516399800|0.15376|0.15376|0.15375|0.15375|5
    BCH-BTC|1516399620|0.1538|0.1538|0.15376|0.15376|2.5832529299999996
    BCH-BTC|1516399560|0.15439|0.15439|0.15439|0.15439|0.09186857

Export to CSV
-------------

The data can easily be exported to CSV:

    $ sqlite3 gdax.sqlite3
    sqlite> .mode csv
    sqlite> .headers on
    sqlite> .output data.csv
    sqlite> SELECT * FROM candles;
    sqlite> .quit

The data will be in a file called `data.csv`:

    $ head data.csv
    market,time,open,high,low,close,volume
    BCH-BTC,1516219140,0.15032,0.15127,0.15032,0.15127,5.197920569999999
    BCH-BTC,1516219080,0.15015,0.15032,0.15,0.15032,10.3002287
    BCH-BTC,1516218900,0.15015,0.15015,0.15011,0.15011,2.2113686899999996
    BCH-BTC,1516218840,0.15042,0.15042,0.15,0.15011,2.59691718
    BCH-BTC,1516218780,0.15042,0.15042,0.15042,0.15042,5.030391000000001

Import to Pandas
----------------

To import the data into Pandas you have two options. Either use the Sqlite3 db directly:

    import pandas as pd
    import sqlite3

    # Connect to database
    con = sqlite3.connect('gdax.sqlite3')
    c = con.cursor()

    # Read data into pandas dataframe
    sql = 'SELECT * FROM candles'
    df = pd.read_sql_query(sql, con, index_col='time', parse_dates={'time': 's'})
    df = df.astype(float)

Or export the data into a CSV file and use the `read_csv` method (less boilerplate code):

    import pandas as pd

    df = pd.read_csv('gdax.csv', index_col='time', parse_dates=True)
    df.index = pd.to_datetime(df.index, unit='s')
