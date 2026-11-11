# Intentional techincal omission

**Docker**

In a real world project I would be using Docker or other container tool. For a take home evaluation I'm intentionally leaving this out because of the overhead around local network configuration and it's extra bloat not needed to prove out what the project ask is.

**Make**

Usually a tool like make or some other sort of tool would make running tests or managing local environments easier but again it's unecessary overhead for a project like this.

# Goal

We are going to establish the following in part 1 so we have our working baseline pattern.

- Set up and gitignore the virtual env
- Django setup and project init using Djangos project boiler plate setup
- Table setup with Django migration(s) 
- Single GET endpoint that is `GET .../tanks/{tank_id}` which returns the basic info about the tank
- We will establish the API -> Service Layer -> Repository Layer pattern
- We will establish the test pattern(s)

When all of this is set up my goal should be that I can using the terminal or tool like Postman/Insomnia hit our endpoint and see a basic response on the GET endpoint. I should be able to log in to the Django admin dashboard and see our tables

# Project virtual env

This is set up and we need to be using the .venv. I've already gitignored it but any python commands need to be using this and the sessions should be scoped into it.

# Django setup

The django admin startproject commmand will set this up

```shell
django-admin startproject dashfuel dashfuelapp
```

# Database setup

Tables will be `tank` and `tank_volume`. I'm not familiar with Django's table schema patterns so if Django offers proper data types out of the box we can use those, otherwise we need to be using something like `Pydantic` and/or `SQLAlchemy` for ensuring types are set up appropriately.

**Tables**

```
Table name: 
tank

Columns:
id: int PK auto increment 
name: string (nullable false)
created_at: datetime (UTC) auto created on insert
updated_at: datetime (UTC) auto created on initial insert and then auto updated on any changes
```

```
Table name: 
tank_volume

Columns:
id: int PK auto increment 
tank_id: FK to tank.id 
volume: float (nullable false)
created_at: datetime (UTC) auto created on insert
updated_at: datetime (UTC) auto created on initial insert and then auto updated on any changes
```

# Endpoint and data retrieval for CRUD

Our CRUD enpoint(s) are going to follow this pattern
```
API (Basic checks) -> Service Layer (business logic layer) -> Repository Layer (DB data access)
```

When we get to the service and repository layer I want to set up `abstract to concrete` class/function pattern as well.
- We can discuss this further as we implement but this needs to be 

We will consider `dependency injection` later unless it makes sense to get it set up out of the gate. If we are going to do dependency injection out of the gate, let's go ahead and get a `dependencies.py` or the Django equivallent set up.

Simple starter GET API output
```json
Request 
GET .../tanks/{tank_id}

Response 200
{
    "id": int
    "name": str
    "created_at": datetime 
    "updated_at": datetime
}
```

In the later steps we can discuss responses for 4xx or 5xx but for now just use a basic 4xx if the ID lookup doesn't return any output.

# Tests

We should make use of fixtures where we can and I'd pref we set these fixtures up inside of a `conftest.py` or whatever the Django version of this is. The rule of thumb is to build fixtures in there and when needed do a `copy or deepcopy`. Deep copy is if we need to mutate some value for a given test since just copy will chage the object for other test which we don't want.

Out of the gate we need to have our test patterns established for CRUD but our only tests right now will be as follows.
- API response we should mock out DB calls here and we can mock out service calls. The goal is to ensure the API response structure is valid and as expected for 200 and 4xx
- Service layer. If a service layer is a straight up pass through to the DB layer then ignore it
- Repository (DB layer) ensure fetching data from the DB works as expected

# Finishing out part 1

Once our full setup is done and we have the patterns in place to satisfy the GET endpoint, we need to create the rest of the CRUD operations. 
GET is done for Tanks so now we need to do the other operations

**Tank**

POST
```json
Endpoint .../api/v1/tanks

Payload
{
    "name": str required,
    "location": str required,
    "timezone": str required
}
```

GET - already done

PATCH
```json
Endpoint .../api/v1/tanks/{tank_id}

4xx if tank not found (bail early) - first operation should be a check if the tank even exists

Payload
{
    "name": str optional,
    "location": str optional,
    "timezone": str optional 
}
```

DELETE
```json
Endpoint .../api/v1/tanks/{tank_id}

4xx if tank not found (bail early) - first operation should be a check if the tank even exists

2xx response doesn't need to return any data it can just return a 2xx OK response
```

NOTE: remeber, soft delete here setting the deleted at as UTC now

**Tank Volume**

- ***NOTE: POST/PATCH/DELETE endpoints here MUST first validate the tank even exists. If it doesn't bail early***
- ***NOTE: This is for the Tank Volume data specifically, NOT for getting readings by tank***
- ***NOTE: Nesting tank volumes under the tank pattern makes sense because a reading doesn't mean much without it's tank***

POST
```json
Endpoint .../api/v1/tanks/{tank_id}/tank_volume

NOTE: I'm going to suggest an array of volume readings in case of a backfil or reason to have multiple at a time

Payload
[
    {
        "volume": float/decimal
    },
    ...
]

Response
[
    {
        "id": int,
        "volume": float/decimal,
        "created_at": datetime,
        "updated_at": datetime
    },
    ...
]
```

GET
```json
Endpoint .../api/v1/tanks/{tank_id}/tank_volume

NOTE: I'm going to suggest an array of readings response with pagination

Response
[
    {
        "id": int,
        "volume": float/decimal,
        "created_at": datetime,
        "updated_at": datetime
    },
    ...
]
```

PATCH
```json
Endpoint .../api/v1/tanks/{tank_id}/tank_volume/{tank_volume_id}

NOTE: We need to make sure the `tank_volume_id` exists otherwise bail early

Payload
{
    "volume": float/decimal,
}

Response
[
    {
        "id": int,
        "volume": float/decimal,
        "created_at": datetime,
        "updated_at": datetime
    }
]
```

DELETE
```json
Endpoint .../api/v1/tanks/{tank_id}/tank_volume/{tank_volume_id}

NOTE: We need to make sure the `tank_volume_id` exists otherwise bail early

2xx response doesn't need to return any data it can just return a 2xx OK response
```