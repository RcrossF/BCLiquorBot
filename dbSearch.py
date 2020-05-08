import json
import os
import requests
import boto3
import decimal
import copy

TOP_N_RESULTS = int(os.environ['TOP_N_RESULTS'])
RETURN_MODAL_TEMPLATE = json.loads(os.environ['RETURN_MODAL_TEMPLATE'])
MODAL_DRINK_CARD_TEMPLATE = json.loads(os.environ['MODAL_DRINK_CARD_TEMPLATE'])
MODAL_LOCATION_CARD_TEMPLATE = json.loads(os.environ['MODAL_LOCATION_CARD_TEMPLATE'])
DIVIDER_TEMPLATE = json.loads(os.environ['DIVIDER_TEMPLATE'])
PRODUCT_URL_BASE = os.environ['PRODUCT_URL_BASE']
NOT_FOUND_IMAGE = os.environ['NOT_FOUND_IMAGE']
STORE_NAME_MAP = json.loads(os.environ['STORE_NAME_MAP'])
BOT_TOKEN = os.environ["BOT_TOKEN"]

PRODUCT_TABLE = os.environ['PRODUCT_TABLE']
table = boto3.resource('dynamodb').Table(PRODUCT_TABLE)

req = requests.Session()
req.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'})

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
        
def process_search(maxPrice=0, drink_type="all", filterStores=[], only_open_stores=True, response_url=None):
    # Query cache, filtering on applicable criteria
    # Not a great way to represent max price, ideally we would multiply item's price by 1.15(15% tax) but dynamodb doesn't support math in queries
    # t = dt.now()
    response = table.scan(
        FilterExpression = "(price <= :maxPrice OR :maxPrice <= :zero) \
                            AND (:drink_type = :all \
                                OR (contains(#drink_type, :drink_type) \
                                    OR contains(category, :drink_type)))",
        ExpressionAttributeValues = {":maxPrice": decimal.Decimal(maxPrice*0.87),
                                    ":drink_type": drink_type,
                                    ":all": "all",
                                    ":zero": decimal.Decimal(0)
        },  
        ProjectionExpression = 'sku, #prod_name, #drink_type, category, price, inventory, #cash_value, adjValue, alcPerc, #count_in_box, volume, rating, sale, image',
        ExpressionAttributeNames={
                '#prod_name': 'name',
                '#drink_type': 'type',
                '#count_in_box': 'count',
                '#cash_value': 'value'
        }
    )
    # print(dt.now()-t)
    # print("DB returned response:")
    # print(response)
    # Create listing objects for items in stock at a store we're searching for
    listings = []
    for elem in response['Items']:
        # At least one store we're searching on stocks this item
        stores_in_stock = set(map(str, filterStores))&set([i for i in elem['inventory'].keys()])

        if len(stores_in_stock) > 0:
            listing = Listing(name=elem['name'], 
                            price=float(elem['price']), 
                            drink_type=elem['type'], 
                            count=int(elem['count']), 
                            volume=float(elem['volume']), 
                            alcPerc=elem['alcPerc'], 
                            category=elem['category'], 
                            rating=float(elem['rating']), 
                            sku=elem['sku'], 
                            value=elem['value'], 
                            adjValue=float(elem['adjValue']), 
                            sale=float(elem['sale']), 
                            image=elem['image'])
            
            listing.inventory = {k:int(v) for k,v in elem['inventory'].items() if int(k) in filterStores}
            listings.append(listing)

    # Sort on adjusted value
    listings.sort(key=lambda k: k.adjValue, reverse=True)

    del listings[TOP_N_RESULTS:] #Only take top N results

    user_return_modal = RETURN_MODAL_TEMPLATE
    user_return_modal['blocks'][0]['text']['text'] = user_return_modal['blocks'][0]['text']['text'].replace('N', str(TOP_N_RESULTS))
    user_return_modal['blocks'].append(DIVIDER_TEMPLATE)

    # Fill in modal to return to user
    for listing in listings:
        print("Processing {}".format(listing.name))
        card = copy.deepcopy(MODAL_DRINK_CARD_TEMPLATE)
        location = copy.deepcopy(MODAL_LOCATION_CARD_TEMPLATE)


        if listing.volume >= 1:
            volume = '{}L'.format(listing.volume)
        elif listing.count > 1:
            volume = '{}x{}ml cans'.format(listing.count, listing.volume*1000)
        else:
            volume = '{}mL'.format(listing.volume*1000)
            
        stars = listing.rating*0.75 if listing.rating <= 3 else round(listing.rating, 0)
        # Price has tax and bottle deposit added
        if listing.count == 1:
            volume = volume.replace('s','')
            
        if listing.sale > 0:
            sale = " *_{}% off_*".format(round(listing.sale, 0))
        else:
            sale = ""
        card['text']['text'] = card['text']['text'] \
            .replace('{liquor_link}', PRODUCT_URL_BASE+str(listing.sku)) \
            .replace('{drink_name}', listing.name) \
            .replace('{volume}', volume) \
            .replace('{alcPerc}', str(listing.alcPerc)) \
            .replace('{score}', str(listing.adjValue)) \
            .replace('{price}', str(round((listing.price*1.15+(0.1*listing.count if listing.count > 1 else 0.2)),2))) \
            .replace('{value}', str(listing.value)) \
            .replace('{rating}', int(round(listing.rating, 0)) * '★') \
            .replace('{sale}', sale)

        if requests.get(listing.image).status_code == 200:
            card['accessory']['image_url'] = listing.image
        else:
            card['accessory']['image_url'] = NOT_FOUND_IMAGE
        
        stores_string = ""
        for store, stock in listing.inventory.items():
            stores_string+=("{}({} in stock)\n".format(STORE_NAME_MAP[store], stock))

        location['elements'][1]['text'] = location['elements'][1]['text'].replace('{locations}', stores_string)
        
        user_return_modal['blocks'].append(card)
        user_return_modal['blocks'].append(location)
        user_return_modal['blocks'].append(DIVIDER_TEMPLATE)

        # Having problems with card persisting
        card = None
        location = None

    #print(user_return_modal)
    
    try:
        print("URL: {}".format(response_url))
        print("JSON: {}".format(json.dumps(user_return_modal)))
        res = req.post(response_url, headers={'Authorization': BOT_TOKEN, 'Content-type': 'application/json'}, json={"text": user_return_modal['text'],"blocks": user_return_modal['blocks']})
        print(res.text)
    except Exception as e:
        print(e)
        
    return
        
def lambda_handler(event, context):
    process_search(event['max_price'], event['search_term'], event['stores'], False, event['response_url'])
    
    return {
        'statusCode': 200,
        'body': json.dumps('Success')
    }
