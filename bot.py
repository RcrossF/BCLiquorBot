import requests as req
import json

def fetchProducts():
    valWeight = 0.8
    ratingWeight = 0.2

    url = "http://www.bcliquorstores.com/ajax/browse"
    params = dict(size=10000)
    res = req.get(url=url, params=params, timeout=10)
    try:
        data = res.json()
    except req.exceptions.Timeout as e:
        return "BC Liquor is down"
    
    list = [] #to append drinks to
    for sku in data['hits']['hits']:
        if(sku['_source']['currentPrice'] == None or sku['_source']['availableUnits'] == 0): #Skip drinks missing prices or with 0 available units
            continue

        price = float(sku['_source']['currentPrice'])
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
        adjvalue = ((value*valWeight)*2)+(rating*ratingWeight)

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
            adjValue = round(adjvalue, 1)
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
                i = 0
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
               i = 0
               continue
            i += 1

    #Sort on adjusted value
    list.sort(key=lambda k: k['adjValue'], reverse=True)

    topResults = []
    url = "http://www.bcliquorstores.com/stores/search"
    params = dict(
        lat=48.428, #Ideally would get the user's location but this is integrating with slack that doesn't support that so use the middle of victoria witha 5km radius
        lng=-123.365,
        rad=5,
        sku=None
    )

    del list[6:] #Drop all but top 5

    #Append remaining products with location data of stores that carry it and are open now
    i = 0
    while i < len(list):
        params['sku'] = list[i]['sku'] #Set sku

        #make network request, will return all stores that have product in stock
        res = req.get(url=url, params=params)
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
            i = 0
            continue
        i = i+1
        #else:
            #print(("SKU: {} with value rating of {}, adjusted score of {}. Customers rated it {}/5").format(prod['sku'], prod['value'], prod['adjValue'], prod['rating']))

    return list

#filterProducts(maxPrice=30, type="gin", filterStore="fort")