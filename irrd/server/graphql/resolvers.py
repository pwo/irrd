import ariadne

from irrd.conf import config_init, get_setting, RPKI_IRR_PSEUDO_SOURCE
from irrd.server.query_resolver import QueryResolver
from irrd.storage.database_handler import DatabaseHandler
from irrd.storage.preload import Preloader
from irrd.utils.text import to_camel_case
from .schema_generator import SchemaGenerator
from irrd.rpsl.rpsl_objects import OBJECT_CLASS_MAPPING, lookup_field_names
from irrd.storage.queries import RPSLDatabaseQuery
from ...rpki.status import RPKIStatus
from ...scopefilter.status import ScopeFilterStatus

config_init('/Users/sasha/dev/irrd4/local_config.yaml')
dh = DatabaseHandler(readonly=True)
pl = Preloader(enable_queries=True)
# pl._load_routes_into_memory(None)
qr = QueryResolver('', '', pl, dh)

schema = SchemaGenerator()
lookup_fields = lookup_field_names()

def resolve_rpsl_object_type(obj, *_):
    return OBJECT_CLASS_MAPPING[obj['objectClass']].__name__


@ariadne.convert_kwargs_to_snake_case
def resolve_query_rpsl_objects(_, info, **kwargs):
    print(kwargs)
    all_valid_sources = set(get_setting('sources', {}).keys())
    if get_setting('rpki.roa_source'):
        all_valid_sources.add(RPKI_IRR_PSEUDO_SOURCE)
    sources_default = set(get_setting('sources_default', []))

    query = RPSLDatabaseQuery(column_names=None, ordered_by_sources=False, enable_ordering=False)
    query.rpki_status([RPKIStatus.not_found, RPKIStatus.valid])
    query.scopefilter_status([ScopeFilterStatus.in_scope])

    if 'rpsl_pk' in kwargs:
        query.rpsl_pks(kwargs['rpsl_pk'])
    if 'object_class' in kwargs:
        query.object_classes(kwargs['object_class'])
    if 'sources' in kwargs:
        query.sources(kwargs['sources'])
    elif sources_default != all_valid_sources:
        query.sources(list(sources_default))
    for attr, value in kwargs.items():
        if attr in lookup_fields:
            query.lookup_attrs_in([attr.replace('_', '-')], value)

    if kwargs.get('sql_debug'):
        info.context['sql_queries'] = [repr(query)]

    for row in dh.execute_query(query):
        # TODO: try to restrict retrieved columns on what was requested
        graphql_result = dict(
            objectClass=row['object_class'],
            rpslPk=row['rpsl_pk'],
            updated=row['updated'],
            source=row['source'],
            rpkiStatus=row['rpki_status'].name,
            rpslText=row['object_text'],
            prefixLength=row['prefix_length'],
            asnFirst=row['asn_first'],
            asnLast=row['asn_last'],
        )
        if row['ip_first'] and row['prefix_length']:
            graphql_result['prefix'] = row['ip_first'] + '/' + str(row['prefix_length'])
        if row['asn_first'] and row['asn_first'] == row['asn_last']:
            graphql_result['asn'] = row['asn_first']

        for key, value in row['parsed_data'].items():
            graphql_type = schema.graphql_types[row['object_class']][key]
            if graphql_type == 'String' and isinstance(value, list):
                value = '\n'.join(value)
            graphql_result[to_camel_case(key)] = value
        yield graphql_result


def resolve_database_status(_, info, source=None):
    for name, data in qr.database_status(sources=source).items():
        data['source'] = name
        yield data
