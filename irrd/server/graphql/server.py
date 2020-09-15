import time

from ariadne import make_executable_schema
from ariadne.asgi import GraphQL
from ariadne.types import Extension

from .resolvers import (resolve_query_rpsl_objects, resolve_rpsl_object_type,
                        resolve_database_status)
from .schema_generator import SchemaGenerator

schema = SchemaGenerator()


schema.rpsl_object_type.set_type_resolver(resolve_rpsl_object_type)
schema.query_type.set_field("rpslObjects", resolve_query_rpsl_objects)
schema.query_type.set_field("databaseStatus", resolve_database_status)


class QueryMetadataExtension(Extension):
    def __init__(self):
        self.start_timestamp = None
        self.end_timestamp = None

    def request_started(self, context):
        self.start_timestamp = time.perf_counter()

    def format(self, context):
        data = {}
        if self.start_timestamp:
            data['execution'] = time.perf_counter() - self.start_timestamp
        if 'sql_queries' in context:
            data['sql_queries'] = context['sql_queries']
        return data

@schema.query_type.field("originated")
def resolve_query_originated(_, info, origins):
    for origin in origins:
        yield dict(origin=origin, prefixes=list(qr.routes_for_origin(f'AS{origin}')))


# Create executable GraphQL schema
schema = make_executable_schema(schema.type_defs, *schema.object_types)


# Create an ASGI app using the schema, running in debug mode
app = GraphQL(schema, debug=True, extensions=[QueryMetadataExtension])

