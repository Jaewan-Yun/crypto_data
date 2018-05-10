from matplotlib.finance import candlestick2_ohlc

import matplotlib.pyplot as plt
from poloniex_data import Poloniex


if __name__ == '__main__':

    pair = 'USDT_ETH'
    start = 1470000000
    end = start + 30000

    # download data
    client = Poloniex()
    client.download_data(pair=pair, start=start, end=end)

    # print trade samples
    r = client.get_trades(pair, start, end)
    for row in r[:10]:
        print(row)
    print('...')
    for row in r[-10:]:
        print(row)
    print('Number of trade data: {}'.format(len(r)))
    print('End Trade Data', end='\n\n')

    # print chart samples
    r = client.get_charts(pair=pair, start=start, end=end, interval=300)
    for row in r[:10]:
        print(row)
    print('...')
    for row in r[-10:]:
        print(row)
    print('Number of chart ticks: {}'.format(len(r)))
    print('End Chart Data', end='\n\n')

    # plot chart OHLC
    fig, ax = plt.subplots(1, 1)
    opens, highs, lows, closes = [], [], [], []
    for row in r:
        opens.append(row['open'])
        highs.append(row['high'])
        lows.append(row['low'])
        closes.append(row['close'])
    candlestick2_ohlc(ax=ax,
                      opens=opens[5:],
                      highs=highs[5:],
                      lows=lows[5:],
                      closes=closes[5:],
                      width=0.6, colorup='green', colordown='red')
    fig.canvas.draw()
    plt.pause(1e9)