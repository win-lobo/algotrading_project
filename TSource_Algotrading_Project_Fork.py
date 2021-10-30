#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import hmac
import time
import hashlib
import requests
import math
import pandas as pd
import numpy as np
from urllib.parse import urlencode


# In[ ]:


from secrets_production import API_KEY, API_SECRET


# In[ ]:


KEY = API_KEY
SECRET = API_SECRET
BASE_URL = 'https://api.binance.com' # production base url
#BASE_URL = 'https://testnet.binance.vision' # testnet base url

coin_gecko_api_url = 'https://api.coingecko.com/api/v3/coins/markets'
### Get the top 500 marketcap coins info from CoinGecko 
coins_info = requests.get(f'{coin_gecko_api_url}?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&sparkline=false')
coins_info2 = requests.get(f'{coin_gecko_api_url}?vs_currency=usd&order=market_cap_desc&per_page=250&page=2&sparkline=false')
coins_json = coins_info.json() + coins_info2.json()
# https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&sparkline=false
coin_gecko_list = coins_json
coins_json


# In[ ]:


''' ======  begin of functions, you don't need to touch ====== '''
def hashing(query_string):
    return hmac.new(SECRET.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def get_timestamp():
    return int(time.time() * 1000)


def dispatch_request(http_method):
    session = requests.Session()
    session.headers.update({
        'Content-Type': 'application/json;charset=utf-8',
        'X-MBX-APIKEY': KEY
    })
    return {
        'GET': session.get,
        'DELETE': session.delete,
        'PUT': session.put,
        'POST': session.post,
    }.get(http_method, 'GET')

# used for sending request requires the signature
def send_signed_request(http_method, url_path, payload={}):
    query_string = urlencode(payload, True)
    if query_string:
        query_string = "{}&timestamp={}".format(query_string, get_timestamp())
    else:
        query_string = 'timestamp={}'.format(get_timestamp())

    url = BASE_URL + url_path + '?' + query_string + '&signature=' + hashing(query_string)
    print("{} {}".format(http_method, url))
    params = {'url': url, 'params': {}}
    response = dispatch_request(http_method)(**params)
    return response.json()

# used for sending public data request
def send_public_request(url_path, payload={}):
    query_string = urlencode(payload, True)
    url = BASE_URL + url_path
    if query_string:
        url = url + '?' + query_string
    print("{}".format(url))
    response = dispatch_request('GET')(url=url)
    return response.json()

# used for rounding decimals of orders amount based in Binance calculations 
def round_decimals_down(number:float, decimals:int=2):
    """    Returns a value rounded down to a specific number of decimal places.    """
    if not isinstance(decimals, int):
        raise TypeError("decimal places must be an integer")
    elif decimals < 0:
        raise ValueError("decimal places has to be 0 or more")
    elif decimals == 0:
        return math.floor(number)

    factor = 10 ** decimals
    return math.floor(number * factor) / factor
''' ======  end of functions ====== '''


# In[ ]:


### USER_DATA endpoints, call send_signed_request #####
# get account informtion
# if you can see the account details, then the API key/secret is correct
response = send_signed_request('GET', '/api/v3/account')


# In[ ]:


spot_assets = response['balances']
print (type(spot_assets))


# In[ ]:


my_columns = [
                'Ticker', 
                'Balance', 
                'Locked', 
                'Price', 
                'Value in USD', 
                'Portfolio allocation', 
                'Average Entry Price',
                'Current PNL',
                '% ROE',
                'TP Price'
            ]
assets_dataframe = pd.DataFrame(columns = my_columns)
assets_dataframe


# In[ ]:


for assets in spot_assets:
    ticker = assets['asset']
    locked = float(assets['locked'])
    free = float(assets['free']) 
    i_total_asset = free + locked
    if i_total_asset > 0.0:
        assets_dataframe = assets_dataframe.append(
            pd.Series(
            [
                ticker,
                i_total_asset,
                locked,
                'N/A',
                'N/A',
                'N/A',
                'N/A',
                'N/A',
                'N/A',
                'N/A'
            ],        
            index = my_columns),    
            ignore_index = True
        )        
assets_dataframe


# #### Append price and Value in USD to the Dataframe

# In[ ]:


for i in range(0, len(assets_dataframe)):
    for coins in coin_gecko_list:
        price = float(coins ['current_price'])
        if assets_dataframe.loc[i, 'Ticker'].upper() == coins['symbol'].upper():
            assets_dataframe.loc[i, 'Value in USD'] = price * assets_dataframe.loc[i, 'Balance']
            assets_dataframe.loc[i, 'Price'] = price
assets_dataframe


# ##### Organize dataframe by Value in USD

# In[ ]:


assets_dataframe.sort_values('Value in USD', ascending = False, inplace = True)
assets_dataframe.reset_index(inplace=True)
assets_dataframe.drop('index', axis=1, inplace=True)


# In[ ]:


assets_dataframe


# In[ ]:


sum_assets = assets_dataframe.sum(axis = 0, skipna = True)
total_spot_value = sum_assets.iat[4]
print(f'Total Spot Value: {total_spot_value}')


# In[ ]:


def set_portfolio_allocation(p_total_spot_value):
    
    for i in range(0, len(assets_dataframe)):
        val_usd = assets_dataframe.loc[i, 'Value in USD']
        assets_dataframe.loc[i, 'Portfolio allocation'] = (val_usd/p_total_spot_value)
        
set_portfolio_allocation(total_spot_value)
assets_dataframe


# In[ ]:


def get_orders_by_asset(base_asset, quote_asset):
    params = {
        'symbol': f'{base_asset}{quote_asset}'
    }
    all_orders = send_signed_request('GET', '/api/v3/allOrders', params)
    return all_orders


# In[ ]:


QUOTE_ASSET = ['USDT', 'BUSD', 'BTC']
STABLE_COINS = ['USDT', 'BUSD']


# In[ ]:


buying_df_cols = ['Symbol', 'Status', 'Price', 'Quantity', 'Buying Time']
buying_orders_df = pd.DataFrame(columns = buying_df_cols)
buying_orders_df


# In[ ]:


def search_all_orders_spot (dataframe, list_quote_assets):
    this_all_orders = []
    for i in range(0, len(dataframe)):
        for j in range (0, len(list_quote_assets)):
            base_asset = dataframe.loc[i, 'Ticker']
            if dataframe.loc[i, 'Price'] != 1 and base_asset != list_quote_assets[j]: #avoid to query buying order for stable coins and base/base asset i.e BTC!=BTC
                this_all_orders += get_orders_by_asset(base_asset, list_quote_assets[j])
    return this_all_orders
all_orders = search_all_orders_spot(assets_dataframe, QUOTE_ASSET)


# In[ ]:


# order = all_orders[len(all_orders)-2]
# if type(order) != dict:
#     print ('This in NOT a dictionary')
# else: print ('This is a dictionary')


# In[ ]:


### Getting all the completed buying orders for all assets
for i in range(0, len(all_orders)):
    order = all_orders[i]
    if type(order) == dict:
        if order['status'] == 'FILLED' and order['side'] == 'BUY':
            buying_orders_df = buying_orders_df.append(
                pd.Series(
                [
                    order['symbol'],
                    order['status'],
                    order['price'],
                    order['executedQty'],
                    order['updateTime']
                ],        
                index = buying_df_cols),    
                ignore_index = True
            )


# In[ ]:


buying_orders_df['Price'] = pd.to_numeric(buying_orders_df['Price'])
buying_orders_df['Quantity'] = pd.to_numeric(buying_orders_df['Quantity'])


buying_orders_df


# In[ ]:


print (type(buying_orders_df.loc[0, 'Price']))
print (type(buying_orders_df.loc[0, 'Quantity']))


# In[ ]:


buying_orders_df.sort_values('Buying Time', ascending = False, inplace = True)
buying_orders_df


# In[ ]:


buying_orders_df.reset_index(inplace=True)


# In[ ]:


buying_orders_df


# In[ ]:


buying_orders_df.drop('index', axis=1, inplace=True)


# In[ ]:


buying_orders_df



# Get the index of the last buying order completing the amount of the asset in SPOT
# The index is used to slice the dataframe; the resultant dataframe provides the data for calculating the
# buying weighted average price -- Return -1 in case of error

def get_index_final_buying_orders(df, counter):
    for i in range(0, len(df)):
        counter = counter - df.loc[i, 'Quantity']
        if counter == 0:
            #print(i)
            return i
        elif counter < 0:
            df.loc[i, 'Quantity'] = df.loc[i, 'Quantity'] + counter
            return (i+1)
    return -1
        
# Calculating current Unrealized PnL by asset    
def calculate_current_pnl(index, base_asset, weighted_buying_price):
    current_pnl = 0.0000
    
    if assets_dataframe.loc[index, 'Ticker'] == base_asset:
        current_price = assets_dataframe.loc[index, 'Price']
        balance = assets_dataframe.loc[index, 'Balance']
        current_pnl = (current_price * balance) - (weighted_buying_price * balance)
        return current_pnl
    else:
        return current_pnl
    
         
# Calculating current Unrealized PnL Percentage by asset
def calculate_pnl_perc(index, base_asset, weighted_buying_price):
    pnl_perc = 0.0000

    if assets_dataframe.loc[index, 'Ticker'] == base_asset:
        current_price = assets_dataframe.loc[index, 'Price']
        pnl_perc = (current_price / weighted_buying_price) - 1
        return pnl_perc
    else:
        return pnl_perc


# In[ ]:


quote = 'BUSD'
for i in range(0, len(assets_dataframe)):
    base = assets_dataframe.loc[i, 'Ticker']
    temp_df = buying_orders_df.copy()
    temp_df = temp_df[(buying_orders_df['Symbol'] == f'{base}BUSD') | (buying_orders_df['Symbol'] == f'{base}USDT')]
    temp_df.reset_index(inplace=True)
    temp_df.drop('index', axis=1, inplace=True)

    
    coin_balance = assets_dataframe.loc[i, 'Balance']
    index_last_buying_price = get_index_final_buying_orders(temp_df.copy(), coin_balance)
    
    
    if base != quote and base != 'USDT' and index_last_buying_price >= 0:
        index_last_buying_price = index_last_buying_price + 1
        t_prices_vs_weight_df = temp_df[: index_last_buying_price]
        
        
        #print (f'{base}{index_last_buying_price}')
        
        weighted_avg = round(np.average(t_prices_vs_weight_df['Price'], weights = t_prices_vs_weight_df['Quantity']),2)
        
        
        current_pnl = calculate_current_pnl(i, base, weighted_avg)
        pnl_perc = calculate_pnl_perc(i, base, weighted_avg)
        tp_price = weighted_avg * (1 + 0.2)
        
        assets_dataframe.loc[i, 'Average Entry Price'] = weighted_avg
        assets_dataframe.loc[i, 'Current PNL'] = current_pnl
        assets_dataframe.loc[i, '% ROE'] = pnl_perc
        assets_dataframe.loc[i, 'TP Price'] = tp_price
        
    else:
        assets_dataframe.loc[i, 'Average Entry Price'] = 0.0
        assets_dataframe.loc[i, 'Current PNL'] = 0.0
        assets_dataframe.loc[i, '% ROE'] = 0.0
        assets_dataframe.loc[i, 'TP Price'] = 0.0
        
        
    
assets_dataframe       
    
    
    
#     path = r'_assets/'
#     t_prices_vs_weight_df.to_csv(f'{path}_{base}{quote}.csv')


# In[ ]:


assets_dataframe.to_csv("_assets/portfolio_spot.csv")


# In[ ]:


portfolio_avg_pnl_perc = round(np.average(assets_dataframe['% ROE'], weights = assets_dataframe['Value in USD']),2)


# In[ ]:


portfolio_avg_pnl_perc

