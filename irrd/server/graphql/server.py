import logging
import re
import string
import time

from IPy import IP
from ariadne import make_executable_schema, ScalarType
from ariadne.asgi import GraphQL
from ariadne.contrib.tracing.apollotracing import ApolloTracingExtension
from ariadne.types import Extension
from graphql import ValidationRule, FieldNode, GraphQLError

from .resolvers import (resolve_query_rpsl_objects, resolve_rpsl_object_type,
                        resolve_database_status, resolve_rpsl_object_mnt_by_objs,
                        resolve_rpsl_object_member_of_objs, resolve_rpsl_object_members_by_ref_objs,
                        resolve_rpsl_object_members_objs, resolve_rpsl_object_adminc_objs,
                        resolve_asn_prefixes, resolve_as_set_prefixes,
                        resolve_recursive_set_members, resolve_rpsl_object_techc_objs,
                        resolve_journal)
from .schema_generator import SchemaGenerator
from ...utils.text import clean_ip_value_error

logger = logging.getLogger(__name__)

schema = SchemaGenerator()

schema.rpsl_object_type.set_type_resolver(resolve_rpsl_object_type)
schema.rpsl_contact_union_type.set_type_resolver(resolve_rpsl_object_type)

schema.query_type.set_field("rpslObjects", resolve_query_rpsl_objects)
schema.query_type.set_field("databaseStatus", resolve_database_status)
schema.query_type.set_field("asnPrefixes", resolve_asn_prefixes)
schema.query_type.set_field("asSetPrefixes", resolve_as_set_prefixes)
schema.query_type.set_field("recursiveSetMembers", resolve_recursive_set_members)

schema.rpsl_object_type.set_field("mntByObjs", resolve_rpsl_object_mnt_by_objs)
schema.rpsl_object_type.set_field("journal", resolve_journal)
for object_type in schema.object_types:
    if 'adminCObjs' in schema.graphql_types[object_type.name]:
        object_type.set_field("adminCObjs", resolve_rpsl_object_adminc_objs)
for object_type in schema.object_types:
    if 'techCObjs' in schema.graphql_types[object_type.name]:
        object_type.set_field("techCObjs", resolve_rpsl_object_techc_objs)
for object_type in schema.object_types:
    if 'mbrsByRefObjs' in schema.graphql_types[object_type.name]:
        object_type.set_field("mbrsByRefObjs", resolve_rpsl_object_members_by_ref_objs)
for object_type in schema.object_types:
    if 'memberOfObjs' in schema.graphql_types[object_type.name]:
        object_type.set_field("memberOfObjs", resolve_rpsl_object_member_of_objs)
for object_type in schema.object_types:
    if 'membersObjs' in schema.graphql_types[object_type.name]:
        object_type.set_field("membersObjs", resolve_rpsl_object_members_objs)


@schema.asn_scalar_type.value_parser
def parse_asn_scalar(value):
    try:
        return int(value)
    except ValueError:
        raise GraphQLError(f'Invalid ASN: {value}; must be numeric')


@schema.ip_scalar_type.value_parser
def parse_ip_scalar(value):
    try:
        return IP(value)
    except ValueError as ve:
        raise GraphQLError(f'Invalid IP: {value}: {clean_ip_value_error(ve)}')


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
            data['sql_query_count'] = len(context['sql_queries'])
            data['sql_queries'] = context['sql_queries']

        query = context['request']._json
        query['query'] = query['query'].replace(' ', '').replace('\n', ' ').replace('\t', '')
        client = context['request'].client.host
        logger.info(f'{client} ran query in {data.get("execution")}s: {query}')
        return data


# Create executable GraphQL schema
schema = make_executable_schema(schema.type_defs, *schema.object_types)


# Create an ASGI app using the schema, running in debug mode
app = GraphQL(schema,
              debug=False,
              extensions=[QueryMetadataExtension, ApolloTracingExtension],
              )

