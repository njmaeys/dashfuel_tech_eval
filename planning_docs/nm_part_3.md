# Goal

We need to be able to handle data changes and ensure "freshness" of data in the tank daily sales.

# Changes

Data changes to fuel volume can be a POST to insert a day in a given week, PATCH to modify an existing record, and a DELETE that removes data from a calculation.

# Solution for tech eval

In a production I'd want to put an actual queue system in place. So on POST/PATCH/DELETE called out in `# Changes` section we would fire off an event to something like EventBridge or an SQS Queue for consumption by an external service that way the work isn't in the API which shouldn't be responsible for this type of data update. However, in this tech eval I'll lean on just letting the given routes call the appropriate service(s) directly to make the updates to the stored data in the tank daily sales table.

I we need to make sure the transactions happen and the DB updates appropriately. After that we should then fire off the service(s) needed to refresh the data. Once the data refresh is successful then we can allow the API to return the given data. I need you to call out in comment and in the readme the "appropriate" eventing pattern we would lean on in a production environment.