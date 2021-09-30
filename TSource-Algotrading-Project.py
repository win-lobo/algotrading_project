#!/usr/bin/env python
# coding: utf-8

# In[1]:


import hmac
import time
import hashlib
import requests
import math
import pandas as pd
import numpy as np
from urllib.parse import urlencode


# In[2]:


from secrets_production import API_KEY, API_SECRET


# In[3]:


KEY = API_KEY
SECRET = API_SECRET
BASE_URL = 'https://api.binance.com' # production base url
#BASE_URL = 'https://testnet.binance.vision' # testnet base url

coin_gecko_api_url = 'https://api.coingecko.com/api/v3/coins/markets'
coins_info = requests.get(f'{coin_gecko_api_url}?vs_currency=usd&order=market_cap_desc&per_page=250&page=1&sparkline=false')
coins_info.json()
# https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1&sparkline=false
coin_gecko_list = coins_info.json()


# In[4]:


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


# In[5]:


### USER_DATA endpoints, call send_signed_request #####
# get account informtion
# if you can see the account details, then the API key/secret is correct
response = send_signed_request('GET', '/api/v3/account')


# In[6]:


spot_assets = response['balances']
print (type(spot_assets))


# In[7]:


my_columns = ['Ticker', 'Balance', 'Locked', 'Price', 'Value in USD']
assets_dataframe = pd.DataFrame(columns = my_columns)
assets_dataframe


# In[8]:


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
                'N/A'
            ],        
            index = my_columns),    
            ignore_index = True
        )        
assets_dataframe


# #### Append price and Value in USD to the Dataframe

# In[9]:


for i in range(0, len(assets_dataframe)):
    for coins in coin_gecko_list:
        price = float(coins ['current_price'])
        if assets_dataframe.loc[i, 'Ticker'].upper() == coins['symbol'].upper():
            assets_dataframe.loc[i, 'Value in USD'] = price * assets_dataframe.loc[i, 'Balance']
            assets_dataframe.loc[i, 'Price'] = price
assets_dataframe


# ##### Organize dataframe by Value in USD

# In[10]:


assets_dataframe.sort_values('Value in USD', ascending = False, inplace = True)
assets_dataframe.reset_index(inplace=True)
assets_dataframe.drop('index', axis=1, inplace=True)


# In[11]:


assets_dataframe


# In[12]:


assets_dataframe.sum(axis = 0, skipna = True)


# In[13]:


def get_orders_by_asset(base_asset, quote_asset):
    params = {
        'symbol': f'{base_asset}{quote_asset}'
    }
    all_orders = send_signed_request('GET', '/api/v3/allOrders', params)
    return all_orders


# In[14]:


QUOTE_ASSET = ['USDT', 'BUSD', 'BTC']
STABLE_COINS = ['USDT', 'BUSD']


# In[15]:


buying_df_cols = ['Symbol', 'Status', 'Price', 'Quantity', 'Buying Time']
buying_orders_df = pd.DataFrame(columns = buying_df_cols)
buying_orders_df


# In[16]:


def search_all_orders_spot (dataframe, list_quote_assets):
    this_all_orders = []
    for i in range(0, len(dataframe)):
        for j in range (0, len(list_quote_assets)):
            base_asset = dataframe.loc[i, 'Ticker']
            if dataframe.loc[i, 'Price'] != 1 and base_asset != list_quote_assets[j]: #avoid to query buying order for stable coins and base/base asset i.e BTC!=BTC
                this_all_orders += get_orders_by_asset(base_asset, list_quote_assets[j])
    return this_all_orders
all_orders = search_all_orders_spot(assets_dataframe, QUOTE_ASSET)


# In[17]:


# order = all_orders[len(all_orders)-2]
# if type(order) != dict:
#     print ('This in NOT a dictionary')
# else: print ('This is a dictionary')


# In[17]:


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


# In[18]:


buying_orders_df['Price'] = pd.to_numeric(buying_orders_df['Price'])
buying_orders_df['Quantity'] = pd.to_numeric(buying_orders_df['Quantity'])


buying_orders_df


# In[19]:


print (type(buying_orders_df.loc[0, 'Price']))
print (type(buying_orders_df.loc[0, 'Quantity']))


# In[20]:


buying_orders_df.sort_values('Buying Time', ascending = False, inplace = True)
buying_orders_df


# In[21]:


buying_orders_df.reset_index(inplace=True)


# In[22]:


buying_orders_df


# In[23]:


buying_orders_df.drop('index', axis=1, inplace=True)


# In[24]:


buying_orders_df


# ##### Testing 'Buying Weighted Average Price'

# In[25]:


base = input('Enter the base asset: ')
quote = input('Enter the quote asset: ')


# ###### Getting most recent orders first and buying quantity by base and quote asset

# In[27]:


temp_df = pd.DataFrame()


# In[26]:


temp_df = buying_orders_df[(buying_orders_df['Symbol'] == f'{base}BUSD') | (buying_orders_df['Symbol'] == f'{base}USDT')]

temp_df.reset_index(inplace=True)
temp_df.drop('index', axis=1, inplace=True)
temp_df


# In[27]:


btc_balance = assets_dataframe.loc[3, 'Balance'] 
type(btc_balance)


# #### Get orders that complete the total amount of the asset in Spot

# In[28]:


counter = btc_balance

# Get the index of the last buying order completing the amount of the asset in SPOT
# The index is used to slice the dataframe; the resultant dataframe provides the data for calculating the
# buying weighted average price

def get_index_final_buying_orders(df, counter):
    for i in range(0, len(df)):
        counter = counter - df.loc[i, 'Quantity']
        if counter == 0:
            return i
        elif counter < 0:
            df.loc[i, 'Quantity'] = df.loc[i, 'Quantity'] + counter
            return (i+1)
        
temp_test_df = temp_df[:get_index_final_buying_orders(temp_df, counter)]
temp_test_df

#temp_test_df


# In[29]:


weighted_avg_m3 = round(np.average(temp_test_df['Price'], weights = temp_test_df['Quantity']),2)
weighted_avg_m3


# #### Calculating current Unrealized PnL by asset

# In[33]:


def calculate_current_pnl(base_asset, weighted_buying_price):
    current_pnl = 0.0000
    for i in range(0, len(assets_dataframe)):
        if assets_dataframe.loc[i, 'Ticker'] == base_asset:
            current_price = assets_dataframe.loc[i, 'Price']
            balance = assets_dataframe.loc[i, 'Balance']
            current_pnl = (current_price * balance) - (weighted_buying_price * balance)
    return current_pnl
            
            
            
def calculate_pnl_perc(base_asset, weighted_buying_price):
    pnl_perc = 0.0000
    for i in range(0, len(assets_dataframe)):
        if assets_dataframe.loc[i, 'Ticker'] == base_asset:
            current_price = assets_dataframe.loc[i, 'Price']
            pnl_perc = (current_price / weighted_buying_price) - 1
            return pnl_perc
    return pnl_perc


# In[36]:


current_pnl = calculate_current_pnl(base, weighted_avg_m3)
pnl_perc = calculate_pnl_perc(base, weighted_avg_m3)
print(current_pnl)
print(pnl_perc)
print ("{0:.2f}%".format(pnl_perc * 100))

