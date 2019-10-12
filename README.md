# BCLiquorBot
Based on defined weights this bot will return the top 5 "best" products for you to buy. Currently the available weights are value(proof/$), ratings(bc liquor online store), and current discount %. The default of 90/10/20 seem to work well for finding wildly cheap and strong drinks. With the shoddy algorithm I whipped up the "ideal" drink would get a calculated score of 100 (as alcohol -> 100%, price -> 0, and rating = 5/5), discounts can only increase the score. So theoretically with the default weights a drink that already had a score of 100 could get a maximum score of 120 if it was on a discount of 100% off. In practice this will never happen and the discount just gives a small boost to the score without hurting any drinks that aren't on sale. Word of warning, use common sense when buying the recommendations. I've considered adding a filter to drop all fortified wines

## Usage
1. Create a slack app and add your token to slack.json (Rename slack-sample.json)
2. If you live elsewhere in BC you must update the coordinates in bot.py as they are currently a 5km radius around Victoria for available stores
3. Call the bot with the following syntax:

@botname get "searchTerm(eg. rum, beer, gin, all, etc)" "maxPrice(0 for none)" "store(matches a partial store name, or all)"  
For example:  
@liquorbot get gin 60 all  
or  
@liquorbot get all 0 fairfield
