# Goal 

We need to create a new endpoint to surface two values `Daily total sales` and a `Weekly running average`.

# Data structure for new table

Table name:
tank_daily_sale_results (open to name suggestions)

Columns:
id: int auto increment
tank_id: fk to tank.id
date: date
daily_total_sales: decimal
fuel_load_recieved: bool


Constraint(s):
- Unique on tank_id and date (shouldn't have more than one record per tank per day)

# Endpoint

POST
.../tanks/sales/daily/recalculate
This is simply the mechanism to fire off the calculations to populate the new table. I would rather have a simple daily job or something that can be fired off. The other reason for setting this up in logic is to have the rules in place that an event could fire against.
    - Part 3 will rely on the service layer and logic when we update the PATCH/DELETE. I'll talk more about the eventing I would want to use and the tradeoff to use an in place call during PATCH/DELETE for the eval

GET
.../tanks/sales/daily

This will will have two required query params start/end datetime and an optional repeated query param for tank IDs.

The start/end datetime are pretty straight forward and will let the user specify any timeframe they want but should be limited to a 30 day window for now as a max.

The endpoint itself would surface all tanks the user has access to. NOTE: We don't actually have scopes and permissions so this is more of a wave of hand, just calling out in a normal API pattern this would be something to consider. So in this case we will just return all tanks and the `tank_id` is a repeated query param. Usually repeated because that's an access pattern I'm used to instead of using a string aray we'd have to parse. 
- NOTE: if the IDs are requested and one or many don't exist I want to assume we omit those tanks in the response so it doesn't fail the request. However, if there is a strong disagreement to this pattern, let's discuss
- NOTE: I'm not going to worry about tank pagination here, it would be good to consider this in real scenario but it's going to make the logic complex so let's assume return all resutls for this technical eval

Response structure
```json
# Since we don't have any metadata I'm good with just an array response but open to a `results` envelope if it's a strong suggestion to follow

[
    {
        "tank_id": int,
        "date": date,
        "day_of_week": str - actual day of the week should a client/consumer need it,
        "daily_total_sales": float/decimal,
        "weekly_running_average": float/decimal,
        "fuel_load_recieved": bool - this is usually going to be false but I think it's important for a user of this data to understand that a no sale happened because fuel was increased and unelss we know the full amount dropped off we cannot calculate a real sale or not so this is at least an indicator to the user of something else happening to indicate no sale
    },
    ...
]

```

# Data retrieval rule

I want to make use of the service layer for business rules. I want to keep our DB queries simple and put the business logic on the service layer. There are tradeoffs here and amount of data over time will determine how this evolves but in it's current state the data is small and we should be fine using the service layer as the business rules. This also makes testing of logic simpler.

# Business rules

- A week is defined as `Monday` to `Sunday` so this is the calculated window that these values need to operate in.
- Positive sale is indicated by a volume going down from a previous day meaning some fuel was consumed/purchased
    - Caveate: if there is no reading for the previous day then it is a no sale increase 
        - One exception I would put here is that in a given week if Mon had 20 then Tues no change and then Wed we see 10 
            - I want to call this out as a comment in the code and I think we will write this up somewhere else in our final doc. I don't know enough about this as a business rule but this is something I'd push back on with product but if this is a hard and fast rule then it's a rule of the industry and shouldn't be changed but I think it should be challenged
- Computing across days should always use the `last` reading from the previous day
- For now keep everything in UTC since that's what we are working with. This would be something to consider in a real world application but in this eval just assume all UTC so we can keep it simple
- See note one `fuel_load_recieved` in the json responses and use that as the rule here. Push back where you see fit but that's something I would want to add at some level for a consumer of this data
- Running Average has been well defined for us and we should stick to this as is from product
    - (Sum of daily total sales from Monday up to that day) / (Number of days from Monday up to that day)
- This should all be calculated on the fly, with this amount of data it should be simple to calculate ont the fly. Should this data get very large then it would be time to think about caching with a TTL and a rule in place that'd sit on our PATCH endpoint to call a process that would wipe the cache or refresh the cache since data changes. This is also one of those, let's call it out in the readme as a decision. I also think this talks to part 3

# Update our README

I want to have a section in the README that we call out business rule decisions adheared to but would challenge. The business rules call this out. I also want to call out techincal decisions made with tradeoffs called out ie; the simple DB queries. Help me get our readme updated with these at the top of that after this section.
