import requests
import json
import time
import datetime as dt

valWeight = 0.9
ratingWeight = 0.1
saleWeight = 0.2

req = requests.Session()
req.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:60.0) Gecko/20100101 Firefox/60.0'})

storesUrl = "http://www.bcliquorstores.com/stores/search"
url = "http://www.bcliquorstores.com/ajax/browse"
pageSize = 6000
params = dict(size=pageSize,page=1)
products = []

#Fetches results in buckets of 6000 and merges before returning
def fetch_web():
    res = req.get(url=url, params=params, timeout=10)
    try:
        data = res.json()
        products = data['hits']['hits']
        total_pages = data['hits']['total_pages']

        for i in range(2,total_pages+1):
            params['page'] = i
            res = req.get(url=url, params=params, timeout=10)
            data = res.json()
            if i == total_pages: #The last page will contain n elements that have already come up so that (remaining unique elements + n = pageSize)
                unique_results = data['hits']['total'] % pageSize
                products += data['hits']['hits'][unique_results:]
            else:
                products += data['hits']['hits']

    except req.exceptions.Timeout as e:
        return "BC Liquor is down"

    return products


def fetchProducts():
    prods = fetch_web()
    list = [] #to append drinks to
    for sku in prods:
        if(sku['_source']['currentPrice'] == None or sku['_source']['availableUnits'] == 0): #Skip drinks missing prices or with 0 available units
            continue

        price = float(sku['_source']['currentPrice'])
        regPrice = float(sku['_source']['regularPrice'])
        sale = (1 - (price/regPrice))*100 # % savings
        units = sku['_source']['unitSize'] # #bottles/cans in product
        vol = float(sku['_source']['volume']) # volume/unit
        alc = (float(sku['_source']['alcoholPercentage']))/100 # % alcohol
        totalAlc = (units*vol)*(alc)
        value = (totalAlc/price)*100

        #Adjust value by considering the score from bc liquor's site
        if(sku['_source']['consumerRating'] == None):
            rating = 2.5 # Assume it's perfectly average if no rating is available
        else:
            rating = sku['_source']['consumerRating']

        #2 minute garbage algorithm to weight value and ratings. I'm not a math major
        #Scale all values to 100 so weighting is even
        adjvalue = ((value*40)*valWeight) + ((rating*20)*ratingWeight)+((sale*2)*saleWeight)

        list.append(dict(
            name = sku['_source']['name'],
            price = price,
            type = sku['_source']['productType'],
            count = units,
            volume = vol,
            alcPerc = round(alc*100, 1),
            category = sku['_source']['productCategory'],
            rating = rating,
            sku = sku['_source']['sku'],
            value = round(value, 1),
            adjValue = round(adjvalue, 1),
            sale = sale
        ))

    return list

def filterProducts(maxPrice = 0, type = None, filterStore="all"):
    list = fetchProducts()

    # Filter out all products that are greater than maxPrice or aren't the type we're looking for
    if(maxPrice != 0):
        i = 0
        while i < len(list):
            if (list[i]['price']*1.15) > maxPrice: #Account for tax
                del(list[i])
                continue
            i = i+1

    if(type != None and type != "all"):
        i = 0
        while i < len(list):
            #Sometimes either type or category are None
            if(list[i]['type'] == None):
                list[i]['type'] = ""
            if(list[i]['category'] == None):
                list[i]['category'] = ""

            if ((type.lower() not in list[i]['type'].lower()) and (type.lower() not in list[i]['category'].lower())):
               del(list[i])
               continue
            i += 1

    list.sort(key=lambda k: k['adjValue'], reverse=True) #Sort on adjusted value

    del list[30:]

    list = [i for n, i in enumerate(list) if i not in list[n+1:]] #Filter any remaining duplicates, do it on the top 30 elements only though to save time
    

    del list[20:] #Drop all but top 20, more would take too long to fetch stores. Could be problematic if >5 of the results aren't available at the currently chosen store
    

    params = dict(
        lat=48.428, #Ideally would get the user's location but this is integrating with slack which doesn't support that so use the middle of victoria with a 5km radius
        lng=-123.365,
        rad=5,
        sku=None
    )

    

    #Append remaining products with location data of stores that carry it and are open now
    i = 0
    errors = 0
    while i < len(list):
        params['sku'] = list[i]['sku'] #Set sku

        #make network request, will return all stores that have product in stock
        res = req.get(url=storesUrl, params=params)
        if res.status_code != 200 and errors < 3: #Site sometimes returns a 503 if the item is invalid(?). Try 3 times and drop it if no success is had.
            errors += 1
            print("Bad response, retrying in 1s...")
            time.sleep(1)
            continue
        elif errors >= 3:
            print("No store results for " + list[i]['name'] + "(" + str(list[i]['sku']) + ")" "skipping...")
            del(list[i])
            errors = 0
            continue
            
        errors = 0
        data = res.json()

        list[i]['stores'] = []
        for store in data['stores']:
            if(filterStore.lower() == "all" or filterStore.lower() in store['name'].lower()):
                #If the store is open
                if store['isOpenNow']:
                    list[i]['stores'].append(dict(
                        name = store['name'],
                        closes = store['todayHours']['close'],
                        stock = store['productAvailability'])
                    )

        #If no stores were found drop the product
        if not list[i]['stores'] or len(list[i]['stores']) < 1:
            del(list[i])
            continue
        i = i+1
        #else:
            #print(("SKU: {} with value rating of {}, adjusted score of {}. Customers rated it {}/5").format(prod['sku'], prod['value'], prod['adjValue'], prod['rating']))

    del list[5:] #Drop all but top 5
    return list


#for entry in filterProducts(maxPrice=30, type="gin", filterStore="fort"):
#    print(entry)
#    print("\n")
