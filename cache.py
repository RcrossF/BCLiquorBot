import os
import requests
import boto3
import json
import time
from datetime import datetime as dt
import decimal
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
import bs4
import re

PRODUCT_TABLE = os.environ['PRODUCT_TABLE']
IMAGE_BASE800 = os.environ['IMAGE_BASE800']

table = boto3.resource('dynamodb').Table(PRODUCT_TABLE)

inventoryUrl = "http://www.bcliquorstores.com/ajax/get-product-inventory?sku="
url = "http://www.bcliquorstores.com/ajax/browse"
pageSize = 6000
params = dict(size=pageSize, page=1)
valWeight = 0.9
ratingWeight = 0.1
saleWeight = 0.2

req = requests.Session()
req.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'})


# Helper class to convert a DynamoDB item to JSON.
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)

class Listing:
    def __init__(self, name, price, drink_type, count, volume, alcPerc, category, rating, sku, value, adjValue, sale, image):
        self.name = name
        self.price = price
        self.type = drink_type.lower() if drink_type is not None else None
        self.count = count
        self.volume = volume
        self.alcPerc = alcPerc
        self.category = category.lower() if category is not None else None
        self.rating = rating
        self.sku = sku
        self.value = value
        self.adjValue = adjValue
        self.sale = sale
        self.image = image
        
        
        # To later store inventory (store:stock)
        self.inventory = dict()

    def __eq__(self, other):
        return other and self.sku == other.sku # Shouldn't be duplicate SKUs in BC liquor's stock

    def __hash__(self):
        return hash((self.sku, self.name))

def clear_old_cache():
    response = table.scan(
        FilterExpression = 'last_updated < :24HoursAgo',
        ExpressionAttributeValues = {":24HoursAgo": decimal.Decimal(time.time()-86400)},
        ProjectionExpression = 'sku, last_updated'
    )
    to_remove = [i['sku'] for i in response['Items']]

    for sku in to_remove:
        table.delete_item(
            Key = {'sku': sku}
        )
        
# Fetches results in buckets of 6000 and merges before returning, filtering out prices that are too high and products out of stock

def fetchProducts():
    res = req.get(url=url, params=params, timeout=10)
    try:
        data = res.json()
        products = data['hits']['hits']
        total_pages = data['hits']['total_pages']
    except req.exceptions.Timeout as e:
        print("BC Liquor site error: {}".format(e))
        return

    for i in range(2, total_pages+1):
        params['page'] = i
        res = req.get(url=url, params=params, timeout=10)

        # Skip drinks missing prices or with 0 available units
        data = [i for i in res.json() if i['_source']['currentPrice'] != None and i['_source']['availableUnits'] != 0]
            
        # The last page will contain n elements that have already come up so that (remaining unique elements + n = pageSize)
        if i == total_pages:
            unique_results = data['hits']['total'] % pageSize
            products += data['hits']['hits'][unique_results:]
        else:
            products += data['hits']['hits']    


    listings = set()  # to append drinks to, avoiding duplicates
    for sku in products:
        try:
            price = float(sku['_source']['currentPrice'])
            regPrice = float(sku['_source']['regularPrice'])
            sale = (1 - (price/regPrice))*100  # % savings
            units = sku['_source']['unitSize']  # bottles/cans in product
            vol = float(sku['_source']['volume'])  # volume/unit
            alc = (float(sku['_source']['alcoholPercentage']))/100  # % alcohol
            image = sku['_source']['image'].replace('jpeg', 'jpg') if sku['_source']['image'] is not None else None# Site lists them as jpeg but links actually require jpg
            image = image.replace('http', 'https') # this is because a request to the http version will return a 301 instead of 200 or 404 like we want
            
        except:
            print(f"Error processing {sku['_source']['name']}")
            
        totalAlc = (units*vol)*(alc)
        value = (totalAlc/price)*100
        
        # Don't bother fetching low value products or anything over $100
        if value < 1.2 or price > 100:
            continue
        
        if image is None:
            image = IMAGE_BASE800 + str(sku['_source']['sku']) + ".jpg"

        # Check if remote image exists
        if not requests.head(image, verify=False, timeout=2).ok:
            # If remote image does not exist find a suitable replacement from the web
            
            print('Remote image does not exist for', sku['_source']['name'])
            print('Finding suitable replacement from web')

            search = sku['_source']['name']
            formatted_search = search.replace(' ', '+')
            img_url = 'https://www.bing.com/images/search?q=' + formatted_search

            req_img = req.get(img_url)
            soup = bs4.BeautifulSoup(req_img.content, 'html.parser')
            img = soup.find('img', alt=re.compile('Image result for.*'))

            if img is not None:
                image = img['src']
                print('Remote image found!', image)
            else:
                image = None
                print('Remote image not found :(')  
        
        # Adjust value by considering the score from bc liquor's site
        if(sku['_source']['consumerRating'] == None):
            rating = 2.5  # Assume it's perfectly average if no rating is available
        else:
            rating = sku['_source']['consumerRating']

        # 2 minute garbage algorithm to weight value and ratings. I'm not a math major
        # Scale all values to 100 so weighting is even(?)
        adjvalue = ((value*40)*valWeight) + ((rating*20)
                                             * ratingWeight)+((sale*2)*saleWeight)

        listings.add(Listing(name=sku['_source']['name'], 
                            price=price, 
                            drink_type=sku['_source']['productType'], 
                            count=units, 
                            volume=vol, 
                            alcPerc=round(alc*100, 1), 
                            category=sku['_source']['productCategory'], 
                            rating=rating, 
                            sku=sku['_source']['sku'], 
                            value=round(value, 1), 
                            adjValue=round(adjvalue, 1), 
                            sale=sale, 
                            image=image))

    return listings

# Create or update listings in the db
def update_product_cache():
    listings = fetchProducts()

    # Find the most recently updated items and drop them. Only update 600 entries each run
    response = table.scan(
        FilterExpression = 'last_updated < :2HoursAgo',
        ExpressionAttributeValues = {":2HoursAgo": decimal.Decimal(time.time()-18000)},
        ProjectionExpression = 'sku, last_updated'
    )
    skus_already_updated = [int(i['sku']) for i in response['Items']]
    
    for listing in [elem for elem in listings if elem.sku not in skus_already_updated][:600]:
        inventory = dict()
        # If we get an error wait a few seconds and try again
        errors = 0
        res = request_item_stock(listing.sku)
        while res.status_code != 200 and errors < 3:
            errors += 1
            time.sleep(3)
            res = request_item_stock(listing.sku)
        if errors >= 3:
            print("Too many errors from BC liquor. Stopping.")
            return False

        for store in res.json():
            inventory[store['storeNumber']] = str(store['inventory']['available']) #Dynamodb wants this to be a string

        response = table.update_item(
            Key={'sku': decimal.Decimal(listing.sku)},
            UpdateExpression="set #prod_name = :n, \
                             price = :p, \
                             #drink_type = :t, \
                             #count_in_box = :c, \
                             volume = :vol, \
                             alcPerc = :a, \
                             category = :cat, \
                             rating = :r, \
                             #cash_value = :v, \
                             adjValue = :av, \
                             sale = :s, \
                             image = :i, \
                             inventory = :in, \
                             last_updated = :u",
            ExpressionAttributeValues={
                ':n': listing.name,
                ':p': decimal.Decimal(str(listing.price)),
                ':t': listing.type,
                ':c': decimal.Decimal(str(listing.count)),
                ':vol': decimal.Decimal(str(listing.volume)),
                ':a': decimal.Decimal(str(listing.alcPerc)),
                ':cat': listing.category,
                ':r': decimal.Decimal(str(listing.rating)),
                ':v': decimal.Decimal(str(listing.value)),
                ':av': decimal.Decimal(str(listing.adjValue)),
                ':s': decimal.Decimal(str(listing.sale)),
                ':i': listing.image,
                ':in': inventory,
                ':u': decimal.Decimal(str(time.time()))
            },
            ExpressionAttributeNames={
                '#prod_name': 'name',
                '#drink_type': 'type',
                '#count_in_box': 'count',
                '#cash_value': 'value'
            },
            ReturnValues="UPDATED_NEW"
        )

        time.sleep(0.8)
    return True

def request_item_stock(sku):
    res = req.get(url=inventoryUrl + str(sku))
    return res

def lambda_handler(event, context):
    t = dt.now()
    success = update_product_cache()
    if success:
        print("Cache updated in {}!".format(dt.now()-t))
    else:
        print("Cache update failed after {}".format(dt.now()-t))
    t = dt.now()
    clear_old_cache()
    print("Old Cache purged in {}!".format(dt.now()-t))

    return
