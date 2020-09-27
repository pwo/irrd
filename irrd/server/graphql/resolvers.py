from collections import OrderedDict

import ariadne
import graphql
from IPy import IP

from irrd.conf import config_init, get_setting, RPKI_IRR_PSEUDO_SOURCE
from irrd.server.query_resolver import QueryResolver
from irrd.storage.database_handler import DatabaseHandler
from irrd.storage.preload import Preloader
from irrd.utils.text import to_camel_case
from .schema_generator import SchemaGenerator
from irrd.rpsl.rpsl_objects import OBJECT_CLASS_MAPPING, lookup_field_names
from irrd.storage.queries import RPSLDatabaseQuery, RPSLDatabaseJournalQuery
from ...rpki.status import RPKIStatus
from ...scopefilter.status import ScopeFilterStatus

config_init('/Users/sasha/dev/irrd4/local_config.yaml')
dh = DatabaseHandler(readonly=True)
pl = Preloader(enable_queries=True)
pl._load_routes_into_memory(None)
qr = QueryResolver('', '', pl, dh)

schema = SchemaGenerator()
lookup_fields = lookup_field_names()


def resolve_rpsl_object_type(obj, *_):
    return OBJECT_CLASS_MAPPING[obj.get('objectClass', obj.get('object_class'))].__name__


@ariadne.convert_kwargs_to_snake_case
def resolve_query_rpsl_objects(_, info, **kwargs):
    if not kwargs:
        raise ValueError('You must provide at least one query parameter.')
    if kwargs.get('sql_trace'):
        info.context['sql_trace'] = True

    all_valid_sources = set(get_setting('sources', {}).keys())
    if get_setting('rpki.roa_source'):
        all_valid_sources.add(RPKI_IRR_PSEUDO_SOURCE)
    sources_default = set(get_setting('sources_default', []))

    query = RPSLDatabaseQuery(column_names=_columns_for_fields(info), ordered_by_sources=False, enable_ordering=False)

    if 'rpsl_pk' in kwargs:
        query.rpsl_pks(kwargs['rpsl_pk'])
    if 'object_class' in kwargs:
        query.object_classes(kwargs['object_class'])
    if 'asns' in kwargs:
        query.asns_first(kwargs['asns'])
    if 'text_search' in kwargs:
        query.text_search(kwargs['text_search'])
    if 'rpki_status' in kwargs:
        query.rpki_status(kwargs['rpki_status'])
    else:
        query.rpki_status([RPKIStatus.not_found, RPKIStatus.valid])
    if 'scope_filter_status' in kwargs:
        query.scopefilter_status(kwargs['scope_filter_status'])
    else:
        query.scopefilter_status([ScopeFilterStatus.in_scope])

    ip_filters = 'ip_exact', 'ip_less_specific', 'ip_less_specific_one_level', 'ip_more_specific'
    for ip_filter in ip_filters:
        if ip_filter in kwargs:
            getattr(query, ip_filter)(IP(kwargs[ip_filter]))

    if 'sources' in kwargs:
        query.sources(kwargs['sources'])
    elif sources_default != all_valid_sources:
        query.sources(list(sources_default))

    for attr, value in kwargs.items():
        attr = attr.replace('_', '-')
        if attr in lookup_fields:
            query.lookup_attrs_in([attr], value)

    return rpsl_db_query_to_graphql(query, info)


def resolve_rpsl_object_mnt_by_objs(rpsl_object, info):
    return _resolve_subquery(rpsl_object, info, ['mntner'], pk_field='mntBy')


def resolve_rpsl_object_adminc_objs(rpsl_object, info):
    return _resolve_subquery(rpsl_object, info, ['role', 'person'], pk_field='adminC')


def resolve_rpsl_object_techc_objs(rpsl_object, info):
    return _resolve_subquery(rpsl_object, info, ['role', 'person'], pk_field='techC')


def resolve_rpsl_object_members_by_ref_objs(rpsl_object, info):
    return _resolve_subquery(rpsl_object, info, ['mntner'], pk_field='mbrsByRef')


def resolve_rpsl_object_member_of_objs(rpsl_object, info):
    object_klass = OBJECT_CLASS_MAPPING[rpsl_object['objectClass']]
    sub_object_classes = object_klass.fields['member-of'].referring
    return _resolve_subquery(rpsl_object, info, sub_object_classes, pk_field='memberOf')


def resolve_rpsl_object_members_objs(rpsl_object, info):
    object_klass = OBJECT_CLASS_MAPPING[rpsl_object['objectClass']]
    sub_object_classes = object_klass.fields['members'].referring
    if 'aut-num' in sub_object_classes:
        sub_object_classes.remove('aut-num')
    if 'inet-rtr' in sub_object_classes:
        sub_object_classes.remove('inet-rtr')
    return _resolve_subquery(rpsl_object, info, sub_object_classes, 'members', sticky_source=False)


def _resolve_subquery(rpsl_object, info, object_classes, pk_field, sticky_source=True):
    pks = rpsl_object.get(pk_field)
    # print(f'resolving {rpsl_object} into sub {object_classes} for {pk_field}: {pks}')
    if not pks:
        return
    if not isinstance(pks, list):
        pks = [pks]
    query = RPSLDatabaseQuery(column_names=_columns_for_fields(info), ordered_by_sources=False, enable_ordering=False)
    query.object_classes(object_classes).rpsl_pks(pks)
    if sticky_source:
        query.sources([rpsl_object['source']])
    return rpsl_db_query_to_graphql(query, info)


def resolve_journal(rpsl_object, info):
    query = RPSLDatabaseJournalQuery()
    query.sources([rpsl_object['source']]).rpsl_pk(rpsl_object['rpslPk'])
    for row in dh.execute_query(query):
        response = {to_camel_case(k): v for k, v in row.items()}
        response['operation'] = response['operation'].name
        if response['origin']:
            response['origin'] = response['origin'].name
        yield response


def rpsl_db_query_to_graphql(query: RPSLDatabaseQuery, info):
    if info.context.get('sql_trace'):
        if 'sql_queries' not in info.context:
            info.context['sql_queries'] = [repr(query)]
        else:
            info.context['sql_queries'].append(repr(query))

    for row in dh.execute_query(query):
        graphql_result = {to_camel_case(k): v for k, v in row.items() if k != 'parsed_data'}
        if 'rpki_status' in row:
            graphql_result['rpkiStatus'] = row['rpki_status']
        if row.get('ip_first') and row.get('prefix_length'):
            graphql_result['prefix'] = row['ip_first'] + '/' + str(row['prefix_length'])
        if row.get('asn_first') and row.get('asn_first') == row.get('asn_last'):
            graphql_result['asn'] = row['asn_first']

        for key, value in row.get('parsed_data', dict()).items():
            graphql_type = schema.graphql_types[resolve_rpsl_object_type(row)][key]
            if graphql_type == 'String' and isinstance(value, list):
                value = '\n'.join(value)
            graphql_result[to_camel_case(key)] = value
        yield graphql_result


def resolve_database_status(_, info, sources=None):
    for name, data in qr.database_status(sources=sources).items():
        camel_case_data = OrderedDict(data)
        camel_case_data['source'] = name
        for key, value in data.items():
            camel_case_data[to_camel_case(key)] = value
        yield camel_case_data


def resolve_asn_prefixes(_, info, asns, ip_version=None, sources=None):
    qr.set_query_sources(sources)
    for asn in asns:
        yield dict(asn=asn, prefixes=list(qr.routes_for_origin(f'AS{asn}', ip_version)))


@ariadne.convert_kwargs_to_snake_case
def resolve_as_set_prefixes(_, info, set_names, sources=None, ip_version=None, sql_trace=False):
    if sql_trace:
        qr.enable_sql_trace()
    qr.set_query_sources(sources)
    for set_name in set_names:
        prefixes = list(qr.routes_for_as_set(set_name, ip_version))
        yield dict(rpslPk=set_name, prefixes=prefixes)
    if sql_trace:
        info.context['sql_queries'] = qr.retrieve_sql_trace()


@ariadne.convert_kwargs_to_snake_case
def resolve_recursive_set_members(_, info, set_names, sources=None, sql_trace=False):
    if sql_trace:
        qr.enable_sql_trace()
    qr.set_query_sources(sources)
    for set_name in set_names:
        members = list(qr.members_for_set(set_name, recursive=True))
        yield dict(rpslPk=set_name, members=members)
    if sql_trace:
        info.context['sql_queries'] = qr.retrieve_sql_trace()


def _columns_for_fields(info):
    # Some columns are always retrieved
    columns = {'object_class', 'source', 'parsed_data', 'rpsl_pk'}
    fields = _collect_predicate_names(info.field_nodes[0].selection_set.selections)
    requested_fields = {ariadne.convert_camel_case_to_snake(f) for f in fields}

    for field in requested_fields:
        if field in RPSLDatabaseQuery.columns:
            columns.add(field)
        if field == 'asn':
            columns.add('asn_first')
            columns.add('asn_last')
    return columns


# https://github.com/mirumee/ariadne/issues/287
def _collect_predicate_names(selections):
    predicates = []
    for selection in selections:
        if isinstance(selection, graphql.InlineFragmentNode):
            predicates.extend(_collect_predicate_names(selection.selection_set.selections))
        else:
            predicates.append(selection.name.value)

    return predicates
