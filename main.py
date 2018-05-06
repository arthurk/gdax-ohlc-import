import argparse
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

logger = logging.getLogger()

API_URL = 'https://api.gdax.com'

# "product-id": "trading start day"
# the api doesn't expose the starting dates
# these values have been manually collected
PRODUCTS = {
    'BCH-BTC': '2018-01-17',
    'BCH-USD': '2017-12-20',
    'BCH-EUR': '2018-01-24',

    'BTC-EUR': '2015-04-23',
    'BTC-USD': '2015-01-08',
    'BTC-GBP': '2015-04-21',

    'ETH-BTC': '2016-05-18',
    'ETH-EUR': '2017-05-23',
    'ETH-USD': '2016-05-18',

    'LTC-BTC': '2016-08-17',
    'LTC-USD': '2016-08-17',
    'LTC-EUR': '2017-05-22'
}


def configure_logging(loglevel):
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(loglevel)


def create_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candles (
            market TEXT NOT NULL,
            time TEXT NOT NULL,
            open TEXT NOT NULL,
            high TEXT NOT NULL,
            low TEXT NOT NULL,
            close TEXT NOT NULL,
            volume TEXT NOT NULL,
            PRIMARY KEY (market, time)
        );
    """)


def daterange(start, end, step):
    curr = start
    while curr < end:
        yield curr, curr+step
        curr += step


def get(url, params):
    # todo: handle non-http errors: timeout, ConnectionError, etc.
    # handle error 400: Bad Request – Invalid request format -> exit
    tries = 3
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=(10, 10))
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            # Only 4XX code we want to re-try is 429 (api rate limit)
            # Other client error codes such as "400 Bad Request" or
            # "403 Forbidden" will always fail no matter how often we try
            if e.response.status_code in (429, 500) and (i < tries - 1):
                logger.warning(e)
                logger.info('Re-trying')
                # api rate limit is 3 requests per second
                # we do 1 request per second to be safe
                time.sleep(1)
                continue
            else:
                raise
        break
    return r.json()


def get_candles(product, start_date, end_date=datetime.now()):
    # "your response may contain as many as 300 candles"
    # we need one candle per minute (granularity=60)
    d = timedelta(minutes=300)

    # the most recent values are going to change, to avoid saving them
    # to the database, we will exclude them and fetch them the next run
    end_date = end_date - d

    if end_date < start_date:
        logger.debug(f'start date {start_date} is after end date {end_date}')
        return []

    previous_start_date = start_date.date()
    for start, end in daterange(start_date, end_date, d):
        logger.debug(f'{product} | {start} -> {end} | {start_date} -> {end_date}')

        # logging should only show day-by-day progress
        if start.date() != previous_start_date:
            logger.info(f'{product} | importing {start.date()}')

        params = {'start': start.isoformat(),
                  'end': end.isoformat(),
                  'granularity': 60}
        try:
            data = get(f'{API_URL}/products/{product}/candles', params=params)
        except requests.exceptions.HTTPError as e:
            # if re-trying doesnt work, we skip to next product
            # the next run can resume from latest value
            logger.error('Unable to fetch candles (max-retries exceeded)')
            logger.error(e)
            return

        previous_start_date = start.date()
        yield data


def insert_db(cur, product, candles):
    logger.debug(f'inserting {len(candles)} to db')

    # generator used by sqlite executemany function
    def candle_generator():
        for candle in candles:
            # in rare cases the api returned extra values in the response
            if len(candle) != 6:
                logger.warning(f'Response length invalid: {candle}')
                continue

            # all values are floats, but the sqlite field is TEXT
            # we convert it here
            candle = [str(i) for i in candle]
            candle.insert(0, product)
            yield candle

    cur.executemany("""
    INSERT OR IGNORE INTO candles(market, time, low, high, open, close, volume)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, candle_generator())


def get_start_date(product, cur):
    # if no date was passed, we check the DB for the latest record
    cur.execute('select max(time) from candles where market=?', (product,))
    try:
        start_date = datetime.utcfromtimestamp(int(cur.fetchone()[0]))
        logging.info(f'Resuming from {start_date}')
    except TypeError:
        # if there are no records, we start from 1st trading day
        start_date = datetime.strptime(PRODUCTS[product], '%Y-%m-%d')
        logging.info('No previous data found. Importing full history')
    return start_date


def main():
    # cli args
    parser = argparse.ArgumentParser(description='GDAX Fetcher')
    parser.add_argument('db_file', type=str, help='sqlite3 db file path')
    parser.add_argument('-l', '--loglevel', dest='loglevel',
                        help='Loglevel. DEBUG|INFO|WARNING|ERROR|CRITICAL',
                        default='INFO')
    parser.add_argument('-s', '--start-date', dest='start_date',
                        help='Process candles since given date. YYYY-mm-dd format',
                        default=None)
    parser.add_argument('-p', '--product', dest='product',
                        help='Which product to update',
                        default=None)
    args = parser.parse_args()

    # logging
    configure_logging(args.loglevel)

    # database
    path = str(Path(args.db_file).resolve())
    logger.debug(f'Database: {path}')
    con = sqlite3.connect(path)
    cur = con.cursor()
    create_table(cur)

    # select which products to update
    if args.product:
        products_to_update = {args.product: PRODUCTS[args.product]}
    else:
        products_to_update = PRODUCTS

    logger.info(f'Updating {list(products_to_update)}')
    for i, product in enumerate(products_to_update, 1):
        # if start date was set via cli arg
        if args.start_date is not None:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        else:
            start_date = get_start_date(product, cur)

        log_prefix = f'{i}/{len(products_to_update)} | {product} | '
        logger.info(log_prefix + f'starting from {start_date}')

        for candles in get_candles(product, start_date):
            logger.debug(log_prefix + f'fetched {len(candles)} candles')
            with con:
                insert_db(cur, product, candles)
            # api rate limit is 3 req/sec
            time.sleep(0.5)
    con.close()


if __name__ == '__main__':
    main()
