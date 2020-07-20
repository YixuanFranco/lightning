from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import Permission, Group
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from .models import Menu, Admin, Setting
from .utils import remove_permission, check_page, get_permission

@receiver(pre_save, sender=Menu, dispatch_uid='remove_menu_permission')
def remove_menu_permission(sender, instance, update_fields = [], **kwargs):
    if instance.id:
        old_instance = Menu.objects.get(id=instance.id)
        old_page = old_instance.page
        new_page = instance.page
        old_type = old_instance.type
        new_type = instance.type

        if check_page(old_page, new_page, old_type, new_type):
            remove_permission(old_instance)

        if new_page not in (Menu.PAGE_LIST, Menu.PAGE_DETAIL):
            instance.model = ''
    

@receiver(post_save, sender=Menu, dispatch_uid='set_menu_permission')
def set_menu_permission(sender, instance, update_fields = [], **kwargs):
    _, permission_lable = get_permission(instance)
    Menu.objects.filter(id=instance.id).update(permission=permission_lable)

@receiver(pre_delete, sender=Menu, dispatch_uid='delete_menu_permission')
def delete_menu_permission(sender, instance, **kwargs):
    permission, _ = get_permission(instance)
    if permission:
        permission.group_set.remove(*instance.groups.all().exclude(name='系统管理员'))
        remove_permission(instance)

from django.db.models.signals import m2m_changed
from django.contrib.auth.models import Permission, Group


@receiver(m2m_changed, sender=Menu.groups.through, dispatch_uid='menu_changed')
def menu_changed(sender, instance, model, pk_set, action, **kwargs):
    if model==Group and action in ('post_add', 'post_remove'):
        groups = model.objects.filter(pk__in=list(pk_set))
        print(sender, instance, model, pk_set, action, kwargs)
        permission, _ = get_permission(instance)
        if action == 'post_add':
            permission.group_set.add(*groups)
        if action == 'post_remove':
            permission.group_set.remove(*groups)

def update_setting_config_permission(sender, **kwargs):
    content_type = ContentType.objects.get_for_model(Setting)
    permissions = [*Permission.objects.filter(content_type=content_type).values_list('codename', flat=True)]
    if settings.SETTINGS_CONFIG:
        for setting in settings.SETTINGS_CONFIG:
            codename = setting.get('permission_code',None)
            if codename and (codename not in permissions):
                per = Permission.objects.create(content_type=content_type, codename=codename)