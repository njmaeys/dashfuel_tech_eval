"""Request validation and response shapes (the equivalent of FastAPI's Pydantic models).

Request serializers validate input and build domain dataclasses (to_domain). Response
serializers declare every output field explicitly, so the JSON contract is visible in one place.
"""
