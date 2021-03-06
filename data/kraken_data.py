import time

import requests

import base_data
from dataio import DataIO
import numpy as np
import timeutil


class Kraken(base_data.BaseExchange):

    # Fieldnames are used as header in saved CSV file. All headers should
    # have both date (ISO) and time (UNIX) fieldnames.
    FIELDNAMES = [
        'date',  # engineered from UNIX
        'time',  # native
        'size',  # native
        'price',  # native
        'side',  # native
        'order_type'  # native
    ]
    __MAX_LIMIT = 1000  # API limit on maximum trades returned
    __BASE_URL = 'https://api.kraken.com/0'  # base API url

    def __init__(self, savedir='exchange_data\\kraken', timeout=600):
        self._savedir = savedir
        self._timeout = timeout

    def __get(self, path, payload, max_retries=100):
        r = None
        for retries in range(1, max_retries + 1):
            try:
                r = requests.get(self.__BASE_URL + path,
                                 params=payload,
                                 timeout=self._timeout)
                # HTTP not OK or Kraken error
                while not r.ok or len(r.json()['error']) > 0:
                    time.sleep(3 * retries)
                    print('Kraken\t| Retries : {}'.format(retries))
                    r = requests.get(self.__BASE_URL + path,
                                     params=payload,
                                     timeout=self._timeout)
                    retries += 1
            except Exception as e:
                print('Kraken\t| {}'.format(e))
                time.sleep(10)
                continue
            break
        return r.json()['result']

    def __get_slice(self, pair, since):
        """Makes a call to the API that fetches trade data.

        Example call:
            https://api.kraken.com/0/public/Trades?pair=XXBTZUSD&since=1526008794000000000

        Args:
            pair (str): Currency pair.
            since (int): UNIX of oldest trade data (inclusive).

        Returns:
            Trade data since time `since`, up to maximum trade list of size
            `self.__MAX_LIMIT`, in the order of increasing UNIX.
        """
        params = {'pair': pair,
                  'since': int(since * 1e9)}
        # old -> new
        return self.__get('/public/Trades', params)[pair]

    def __to_dict(self, data):
        """Convert API trade data response into a list of dict.

        Args:
            data (list of list): API trade data response.

        Returns:
            List of python dict.
        """
        new_data = []
        for row in data:
            row_dict = {'date': timeutil.unix_to_iso(row[2]),
                        'time': row[2],
                        'size': row[1],
                        'price': row[0],
                        'side': row[3],
                        'order_type': row[4]}
            new_data.append(row_dict)
        return new_data

    def __find_start_trade_time(self, pair, start_unix):
        """Find a valid start UNIX, given arbitrary start UNIX.

        Args:
            pair (str): Currency pair.
            start (int): Start UNIX of trade data check if valid.

        Returns:
            A valid start UNIX, either `start_unix` or UNIX of first trade
            ever made for `pair`.
        """
        # check if no pair trades exist before start_unix
        r = self.__get_slice(pair, 0)
        oldest_t = r[-1][2]
        if oldest_t > start_unix:
            print('Kraken\t| No trades exist for {} before {}'.format(
                pair, start_unix))
            return oldest_t
        return start_unix

    def download_data(self, pair, start, end):
        """Download trade data and store as .csv file.

        Args:
            pair (str): Currency pair.
            start (int): Start UNIX of trade data to download.
            end (int): End UNIX of trade data to download.
        """
        dataio = DataIO(savedir=self._savedir, fieldnames=self.FIELDNAMES)
        if dataio.csv_check(pair):
            newest_t = float(dataio.csv_get_last(pair)['time'])
        else:
            newest_t = self.__find_start_trade_time(pair, start)

        while newest_t < end:
            # old -> new
            r = self.__get_slice(pair, newest_t + 1e-4)

            # list to dict
            r = self.__to_dict(r)

            # save to file
            dataio.csv_append(pair, r)

            # break condition
            if len(r) < self.__MAX_LIMIT:
                break

            # prepare next iteration
            newest_t = float(r[-1]['time'])
            print('Kraken\t| {} : {}'.format(
                timeutil.unix_to_iso(newest_t), pair))

        print('Kraken\t| Download complete : {}'.format(pair))

    def get_trades(self, pair, start, end):
        """Get trade data from .csv file.

        Args:
            pair (str): Currency pair.
            start (int): Start UNIX of trade data to fetch.
            end (int): End UNIX of trade data to fetch.

        Returns:
            List of trade events, from old to new data.
        """
        dataio = DataIO(savedir=self._savedir, fieldnames=self.FIELDNAMES)
        if dataio.csv_check(pair):
            data = dataio.csv_get(pair)
        else:
            raise ValueError(
                'Kraken\t| No trades downloaded: {}'.format(pair))

        # look for start and end row indices
        start_index = None
        end_index = None
        for i, timestamp in enumerate(data['time']):
            if float(timestamp) <= float(start):
                start_index = i
            if float(timestamp) <= float(end):
                end_index = i

        # filter by requested date range
        new_data = {}
        for col_name in data:
            new_data[col_name] = data[col_name][start_index: (end_index + 1)]
        return new_data

    def get_charts(self, pair, start, end, interval=60):
        """Convert trade data to OHLC format.

        Args:
            pair (str): Currency pair.
            start (int): Start UNIX of chart data to fetch.
            end (int): End UNIX of chart data to fetch.
            interval (int): Interval, in seconds.

        Returns:
            List of ticks, from old to new data.
        """
        # get trade data, from oldest to newest trades
        trade_data = self.get_trades(pair, start, end)
        chart_data = {
            'time': [],
            'open': [],
            'high': [],
            'low': [],
            'close': [],
            'volume': [],
            'weighted_average': [],
            'n_trades': [],
            'n_sells': [],
            'sell_volume': [],
            'sell_weighted_average': [],
            'n_buys': [],
            'buy_volume': [],
            'buy_weighted_average': [],
        }

        # bucket trade data into intervals
        timepoints = np.arange(start + interval, end, interval)
        index = 0
        for t in timepoints:
            lower_t = t - interval + 1  # exclusive
            upper_t = t  # inclusive

            # collect all trade data between lower_t and upper_t
            bucket = {label: [] for label in self.FIELDNAMES}
            while (index < len(trade_data['time']) and
                   float(trade_data['time'][index]) <= float(upper_t)):
                if float(trade_data['time'][index]) >= float(lower_t):
                    for label in trade_data:
                        bucket[label].append(trade_data[label][index])
                index += 1

            # process trades into tick
            tick = {}
            tick['time'] = upper_t

            if len(bucket['time']) > 0:
                # collect OHLC data from trades
                prices = np.asarray(bucket['price'], dtype=np.float32)
                sizes = np.asarray(bucket['size'], dtype=np.float32)

                # set current opening price to last closing price
                if len(chart_data['close']) > 0:
                    carry_forward_price = chart_data['close'][-1]
                else:
                    carry_forward_price = prices[0]

                # calculate chart OHLC
                tick['open'] = carry_forward_price
                tick['high'] = np.max(prices)
                tick['low'] = np.min(prices)
                tick['close'] = prices[-1]
                tick['volume'] = np.sum(sizes)
                tick['weighted_average'] = (np.sum(prices * sizes) /
                                            tick['volume'])

                # collect trade sell/buy volume and prices
                buy_sizes = np.asarray(
                    [size for size, side in
                     zip(bucket['size'],
                         bucket['side']) if side == 'buy' or side == 'b'],
                    dtype=np.float32)
                buy_prices = np.asarray(
                    [price for price, side in
                     zip(bucket['price'],
                         bucket['side']) if side == 'buy' or side == 'b'],
                    dtype=np.float32)
                sell_prices = np.asarray(
                    [price for price, side in
                     zip(bucket['price'],
                         bucket['side']) if side == 'sell' or side == 's'],
                    dtype=np.float32)
                sell_sizes = np.asarray(
                    [size for size, side in
                     zip(bucket['size'],
                         bucket['side']) if side == 'sell' or side == 's'],
                    dtype=np.float32)

                # calculate chart sell/buy volume and weighted average
                if len(buy_sizes) > 0:
                    tick['buy_volume'] = np.sum(buy_sizes)
                    tick['buy_weighted_average'] = (np.sum(buy_prices * buy_sizes) /
                                                    tick['buy_volume'])
                else:
                    tick['buy_volume'] = 0
                    tick['buy_weighted_average'] = carry_forward_price
                if len(sell_sizes) > 0:
                    tick['sell_volume'] = np.sum(sell_sizes)
                    tick['sell_weighted_average'] = (np.sum(sell_prices * sell_sizes) /
                                                     tick['sell_volume'])
                else:
                    tick['sell_volume'] = 0
                    tick['sell_weighted_average'] = carry_forward_price

                # total number of trades
                tick['n_buys'] = len(buy_sizes)
                tick['n_sells'] = len(sell_sizes)
                tick['n_trades'] = tick['n_sells'] + tick['n_buys']

            # carry forward relevant info if no trades within the interval
            else:
                if len(chart_data['close']) > 0:
                    carry_forward_price = chart_data['close'][-1]
                else:
                    carry_forward_price = 0

                tick['low'] = carry_forward_price
                tick['high'] = carry_forward_price
                tick['open'] = carry_forward_price
                tick['close'] = carry_forward_price
                tick['volume'] = 0
                tick['weighted_average'] = carry_forward_price
                tick['sell_volume'] = 0
                tick['sell_weighted_average'] = carry_forward_price
                tick['buy_volume'] = 0
                tick['buy_weighted_average'] = carry_forward_price
                tick['n_sells'] = 0
                tick['n_buys'] = 0
                tick['n_trades'] = 0

            # collect tick data
            for label in tick:
                chart_data[label].append(tick[label])

        return chart_data

    def get_pairs(self):
        """Returns all currency pairs supported by the exchange.

        Returns:
            A list of currency pair strings.
        """
        r = self.__get('/public/AssetPairs', None)
        pairs = []
        for product in r:
            if not '.d' in product:
                pairs.append(product)
        return sorted(pairs)
