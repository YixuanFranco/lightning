import requests
import logging

from django.db import transaction
from django.http import HttpResponse

from rest_framework.exceptions import PermissionDenied

from api_basebone.core import exceptions
from api_basebone.signals import post_bsm_create
from api_basebone.restful.funcs import find_func
from api_basebone.restful.relations import forward_relation_hand, reverse_relation_hand
from api_basebone.drf.response import success_response

from api_basebone.restful.client import user_pip as client_user_pip

log = logging.getLogger(__name__)


def filter_display_fields(data, display_fields):
    """从json数据中筛选，只保留显示的列"""
    if not display_fields:
        """没有限制的情况下，显示所有"""
        return data

    display_fields_set = set()
    for field_str in display_fields:
        items = field_str.split('.')
        for i in range(len(items)):
            display_fields_set.add('.'.join(items[: i + 1]))
    if isinstance(data, list):
        results = []
        for record in data:
            display_record = filter_sub_display_fields(display_fields_set, record)
            results.append(display_record)
        return results
    elif isinstance(data, dict):
        return filter_sub_display_fields(display_fields_set, data)


def filter_sub_display_fields(display_fields_set, record, prefix=''):
    display_record = {}

    # 星号为通配符，该层所有属性都匹配
    if prefix:
        star_key = prefix + '.*'
    else:
        star_key = '*'

    for k, v in record.items():
        if prefix:
            full_key = prefix + '.' + k
        else:
            full_key = k
        exclude_key = '-' + full_key
        if isinstance(v, list):
            if full_key not in display_fields_set:
                continue
            display_record[k] = []
            for d in v:
                sub_record = filter_sub_display_fields(display_fields_set, d, full_key)
                display_record[k].append(sub_record)
        elif isinstance(v, dict):
            if full_key not in display_fields_set:
                continue
            display_record[k] = filter_sub_display_fields(display_fields_set, v, full_key)
        # 负号优先级高于星号
        elif exclude_key in display_fields_set:
            """负号表示该属性不显示"""
            continue
        # 星号优先级高于具体的列名
        elif star_key in display_fields_set:
            """星号为通配符"""
            display_record[k] = v
        elif full_key in display_fields_set:
            display_record[k] = v
    return display_record


def display(genericAPIView, display_fields):
    """查询操作，取名display，避免跟列表list冲突"""
    queryset = genericAPIView.filter_queryset(genericAPIView.get_queryset())

    page = genericAPIView.paginate_queryset(queryset)
    if page is not None:
        """分页查询"""
        serializer = genericAPIView.get_serializer(page, many=True)
        result = filter_display_fields(serializer.data, display_fields)
        response = genericAPIView.get_paginated_response(result)
        result = response.data
    else:
        serializer = genericAPIView.get_serializer(queryset, many=True)
        result = filter_display_fields(serializer.data, display_fields)
    return success_response(result)


def retrieve(genericAPIView, display_fields):
    """获取数据详情"""
    instance = genericAPIView.get_object()
    serializer = genericAPIView.get_serializer(instance)
    result = filter_display_fields(serializer.data, display_fields)
    return success_response(result)


def client_func(genericAPIView, user, app, model, func_name, params):
    """云函数, 由客户端直接调用的服务函数
        """
    func, options = find_func(app, model, func_name)
    if not func:
        raise exceptions.BusinessException(
            error_code=exceptions.FUNCTION_NOT_FOUNT,
            error_data=f'no such func: {func_name} found',
        )

    if options.get('login_required', False):
        if not user.is_authenticated:
            raise PermissionDenied()

    view_context = {'view': genericAPIView}
    params['view_context'] = view_context

    result = func(user, **params)
    # TODO：考虑函数的返回结果类型。1. 实体，2.实体列表，3.字典，4.无返回，针对不同的结果给客户端反馈
    if isinstance(result, requests.Response):
        return HttpResponse(result, result.headers.get('Content-Type', None))
    if isinstance(result, (list, dict)):
        return success_response(result)
    if isinstance(result, genericAPIView.model):
        serializer = genericAPIView.get_serializer(result)
        return success_response(serializer.data)
    return success_response()


def manage_func(genericAPIView, user, app, model, func_name, params):
    """云函数, 由客户端直接调用的服务函数
        """
    # import ipdb; ipdb.set_trace()
    func, options = find_func(app, model, func_name)
    if not func:
        raise exceptions.BusinessException(
            error_code=exceptions.FUNCTION_NOT_FOUNT,
            error_data=f'no such func: {func_name} found',
        )
    if options.get('login_required', False):
        if not user.is_authenticated:
            raise PermissionDenied()
    if options.get('staff_required', False):
        if not user.is_staff:
            raise PermissionDenied()
    if options.get('superuser_required', False):
        if not user.is_superuser:
            raise PermissionDenied()

    view_context = {'view': genericAPIView}
    params['view_context'] = view_context
    result = func(user, **params)

    # TODO：考虑函数的返回结果类型。1. 实体，2.实体列表，3.字典，4.无返回，针对不同的结果给客户端反馈
    if isinstance(result, requests.Response):
        response = HttpResponse(result, result.headers.get('Content-Type', None))
        if 'Content-disposition' in result.headers:
            response['Content-disposition'] = result.headers.get('Content-disposition')
        return response
    if isinstance(result, list) or isinstance(result, dict):
        return success_response(result)
    return success_response()


def client_create(genericAPIView, request):
    """
        这里校验表单和序列化类分开创建

        原因：序列化类有可能嵌套
        """

    with transaction.atomic():
        client_user_pip.add_login_user_data(genericAPIView, request.data)
        forward_relation_hand(genericAPIView.model, request.data)
        serializer = genericAPIView.get_validate_form(genericAPIView.action)(
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        instance = genericAPIView.perform_create(serializer)
        reverse_relation_hand(genericAPIView.model, request.data, instance, detail=False)
        instance = genericAPIView.get_queryset().get(id=instance.id)

        # with transaction.atomic():
        log.debug(
            'sending Post Save signal with: model: %s, instance: %s',
            genericAPIView.model,
            instance,
        )
        post_bsm_create.send(sender=genericAPIView.model, instance=instance, create=True)
        # 如果有联合查询，单个对象创建后并没有联合查询, 所以要多查一次？
        serializer = genericAPIView.get_serializer(
            genericAPIView.get_queryset().get(id=instance.id)
        )
        return success_response(serializer.data)


def manage_create(genericAPIView, request):
    """
        这里校验表单和序列化类分开创建

        原因：序列化类有可能嵌套
        """
    with transaction.atomic():
        forward_relation_hand(genericAPIView.model, request.data)
        serializer = genericAPIView.get_validate_form(genericAPIView.action)(
            data=request.data, context=genericAPIView.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        instance = genericAPIView.perform_create(serializer)
        # 如果有联合查询，单个对象创建后并没有联合查询
        instance = genericAPIView.get_queryset().filter(id=instance.id).first()
        serializer = genericAPIView.get_serializer(instance)
        reverse_relation_hand(genericAPIView.model, request.data, instance, detail=False)

        log.debug(
            'sending Post Save signal with: model: %s, instance: %s',
            genericAPIView.model,
            instance,
        )
        post_bsm_create.send(sender=genericAPIView.model, instance=instance, create=True)
    return success_response(serializer.data)


def client_update(genericAPIView, request, partial):
    """全量更新数据"""
    with transaction.atomic():
        client_user_pip.add_login_user_data(genericAPIView, request.data)
        forward_relation_hand(genericAPIView.model, request.data)

        # partial = kwargs.pop('partial', False)
        instance = genericAPIView.get_object()

        serializer = genericAPIView.get_validate_form(genericAPIView.action)(
            instance, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        instance = genericAPIView.perform_update(serializer)

        reverse_relation_hand(genericAPIView.model, request.data, instance)
        instance = genericAPIView.get_queryset().get(id=instance.id)

        # with transaction.atomic():
        log.debug(
            'sending Post Update signal with: model: %s, instance: %s',
            genericAPIView.model,
            instance,
        )
        post_bsm_create.send(sender=genericAPIView.model, instance=instance, create=False)

        serializer = genericAPIView.get_serializer(
            genericAPIView.get_queryset().get(id=instance.id)
        )
        return success_response(serializer.data)


def manage_update(genericAPIView, request, partial):
    """全量更新数据"""

    with transaction.atomic():
        forward_relation_hand(genericAPIView.model, request.data)

        # partial = kwargs.pop('partial', False)
        instance = genericAPIView.get_object()
        serializer = genericAPIView.get_validate_form(genericAPIView.action)(
            instance,
            data=request.data,
            partial=partial,
            context=genericAPIView.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)

        instance = genericAPIView.perform_update(serializer)
        serializer = genericAPIView.get_serializer(instance)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        reverse_relation_hand(genericAPIView.model, request.data, instance)

    with transaction.atomic():
        log.debug(
            'sending Post Update signal with: model: %s, instance: %s',
            genericAPIView.model,
            instance,
        )
        post_bsm_create.send(sender=genericAPIView.model, instance=instance, create=False)
    return success_response(serializer.data)


def destroy(genericAPIView, request):
    """删除数据"""
    instance = genericAPIView.get_object()
    genericAPIView.perform_destroy(instance)
    return success_response()


def delete_by_conditon(genericAPIView):
    """按查询条件删除"""
    queryset = genericAPIView.filter_queryset(genericAPIView.get_queryset())
    deleted, rows_count = queryset.delete()
    result = {'deleted': deleted}

    return success_response(result)


def update_by_conditon(genericAPIView, set_fields):
    queryset = genericAPIView.filter_queryset(genericAPIView.get_queryset())
    count = queryset.update(**set_fields)
    result = {'count': count}
    return success_response(result)
