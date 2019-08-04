# BCLiquorBot
Based on defined weights this bot will return the top 5 "best" products for you to buy. Currently the available weights are value(proof/$) and ratings(bc liquor online store). The default of 80/20 seem to work well for finding wildly cheap and strong drinks.

## Usage
1. Create a slack app and add your token to slack.py
2. If you live elsewhere in BC you must update the coordinates in bot.py as they currently use a 5km radius around Victoria for available stores
3. Call the bot with the following syntax:

@botname get "searchTerm(eg. rum, beer, gin, all, etc)" "maxPrice(0 for none)" "store(matches a partial store name, or all)"
For example:
@liquorbot get gin 60 all
@liquorbot get all 0 fairfield
