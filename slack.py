import os
import sys
import time
import re
import json
import bot
import traceback
from slackclient import SlackClient

try:
    with open('slack.json') as f:
        token = json.load(f)
except:
    print("Error loading file")
    sys.exit(0)

starterbot_id = None
slack_client = SlackClient(token['bot_token'])
# constants
RTM_READ_DELAY = 1 # 1 second delay between reading from RTM
BOOK_COMMAND = "get"
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"

def parse_bot_commands(slack_events):
    """
        Parses a list of events coming from the Slack RTM API to find bot commands.
        If a bot command is found, this function returns a tuple of command and channel.
        If its not found, then this function returns None, None.
    """
    for event in slack_events:
        if event["type"] == "message" and not "subtype" in event:
            user_id, message = parse_direct_mention(event["text"])
            if user_id == starterbot_id:
                return message, event["channel"]
    return None, None

def parse_direct_mention(message_text):
    """
        Finds a direct mention (a mention that is at the beginning) in message text
        and returns the user ID which was mentioned. If there is no direct mention, returns None
    """
    matches = re.search(MENTION_REGEX, message_text)
    # the first group contains the username, the second group contains the remaining message
    return (matches.group(1), matches.group(2).strip()) if matches else (None, None)

def handle_command(command, channel):
    """
        Executes bot command if the command is known
    """
   
    # This is where you start to implement more commands!
    if command.startswith(BOOK_COMMAND):
        #try:
        sendMessage(channel, "Processing...")
        searchTerm = command.split(' ')[1]
        maxPrice = command.split(' ')[2]
        store = command.split(' ')[3]
        if not store:
            store = "all"
        
        products = bot.filterProducts(float(maxPrice), searchTerm, store)
        if len(products) == 0:
            sendMessage(channel, "Nothing found")
        elif type(products) is str:
            sendMessage(channel, products)
        else:
            try:
                sendMessage(channel, "Based on the weights of: 90% value 10% ratings, here's what I found for *" + searchTerm + "*:")
                for prod in products:

                    #Rough estimate of bottle deposit
                    if(prod['volume'] >= 2):
                        perBottle = 0.2
                    else:
                        perBottle = 0.1

                    #PST liquor and GST 15%, then bottle deposit
                    price = round((prod['price']*1.15) + (perBottle*prod['count']),2)

                    #If item is not on sale don't append any sale text
                    if prod['sale'] == 0: 
                        sale = ""
                    else:
                        sale = "*" + str(round(prod['sale'], 0)) + "% off*"

                    #If we're filtering by store don't bother to append available stores and just give stock
                    if store is None or store == 'all': 
                        stores = "Available at " + str(prod['stores'])
                    else:
                        stores = "Stock: *" + str(prod['stores'][0]['stock']) + "*"

                    sendMessage(channel, "*Score: {}* _Raw Value: {}_ - *{}* is *{}x{}mL* at *{}%*. *${}* - rated *{}/5* {}. {}".format(
                        prod['adjValue'],
                        prod['value'],
                        prod['name'],
                        prod['count'],
                        prod['volume']*1000,
                        prod['alcPerc'],
                        price,
                        prod['rating'],
                        sale,
                        stores
                        )
                    )

            except Exception as e:
                sendMessage(channel, "Error, try something else")
                sendMessage(channel, None)
                exc_type, exc_obj, exc_tb = sys.exc_info()
                fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                print(exc_type, fname, exc_tb.tb_lineno)
                print(e)

   

def sendMessage(channel, text):
    # Default response is help text for the user
    default_response = "Not sure what you mean. Try *{}* *searchterm(or all)* *maxprice(or 0)* *(optional)store(james, fairfield, hillside, fort, gorge, cedar, saanich)*. For example @liquorbot get gin 30 fort".format(BOOK_COMMAND)

     # Sends the response back to the channel
    slack_client.api_call(
        "chat.postMessage",
        channel=channel,
        text=text or default_response
    )


if __name__ == "__main__":
    if slack_client.rtm_connect(with_team_state=False):
        print("Bot connected and running!")
        # Read bot's user ID by calling Web API method `auth.test`
        starterbot_id = slack_client.api_call("auth.test")["user_id"]
        while True:
            command, channel = parse_bot_commands(slack_client.rtm_read())
            if command:
                handle_command(command, channel)
            time.sleep(RTM_READ_DELAY)
    else:
        print("Connection failed. Exception traceback printed above.")