import os
import requests
from urllib.parse import unquote
import json
import decimal
import boto3
import base64


MODAL = os.environ['MODAL']
HOME_PAGE = os.environ['HOME_PAGE']
BOT_TOKEN = os.environ["BOT_TOKEN"]
ARN = os.environ['SEARCH_FUNCTION_ARN']


def open_home(user_id):
    view = {'type': 'home',
            'title': 
                {'type': 'plain_text',
                 'text': 'Liquor Bot Home'},
                 'blocks': HOME_PAGE}
                 
    print("Opening Home Page...")
    try:
        req = requests.post('https://slack.com/api/views.publish', headers={'Authorization': BOT_TOKEN}, data={"token": BOT_TOKEN, "user_id": user_id, "view": json.dumps(view)})
        
        print(req.text)
    except Exception as e:
        print("Error occured opening home!. {}".format(e))
    
def open_modal(trigger_id):
    try:
        print("Opening Modal...")
        req = requests.post('https://slack.com/api/views.open', headers={'Authorization': BOT_TOKEN}, data={"token": BOT_TOKEN,
                                                                                                            "trigger_id": trigger_id,
                                                                                                            "view": MODAL})
        print(req.text)
    except Exception as e:
        print(e)


def lambda_handler(event, context):
    #open_modal('1234')
    print(f"Received event:\n{event}")
    
    # Sometimes body is base64 encoded
    try:
        body = json.loads(unquote(base64.b64decode(event['body']).decode('utf-8')).replace('payload=',''))
    except:
        body = json.loads(event['body'])
    
    print(body)
    
    # Slack doens't have a consistent place to put event type
    if 'event' in body.keys():
        type = body['event']['type']
    else:
        type = body['type']

    # Modal open requests    
    if type == 'shortcut' or (type == 'block_actions' and body['actions'][0]['value'] == 'find_liquor'):
        open_modal(body['trigger_id'])
    # App homepage
    elif type == 'app_home_opened':
        open_home(body['event']['user'])
    # Search requests
    elif type == 'view_submission':
        client = boto3.client('lambda')
        stores = [int(i['value']) for i in body['view']['state']['values']['stores']['selected_stores']['selected_options']] # I heard you like dictionaries
        search_term = body['view']['state']['values']['search']['query']['value']
        max_price = body['view']['state']['values']['max_price']['max_price']['value']

        try:
            max_price = float(max_price)
        except:
            print("Could not cast max price to float")
            return {'statusCode': 500, 'body': "Max price must be a number"}

        response = client.invoke(FunctionName=ARN,
                             InvocationType='Event',
                             Payload=json.dumps(
                                 {
                                     "max_price": max_price,
                                     "search_term": search_term,
                                     "stores": stores,
                                     "response_url": body['response_urls'][0]['response_url']
                             }
                             ))
    

    return {
        'statusCode': 200
    }