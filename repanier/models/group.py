# -*- coding: utf-8

from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.utils.translation import ugettext_lazy as _

from repanier.models.customer import Customer, customer_pre_save, customer_post_delete


class Group(Customer):
    class Meta:
        proxy = True
        verbose_name = _("Group")
        verbose_name_plural = _("Groups")


@receiver(pre_save, sender=Group)
def group_pre_save(sender, **kwargs):
    customer_pre_save(sender, **kwargs)
    group = kwargs["instance"]
    group.is_group = True
    group.may_order = False
    group.delivery_point = None
    # find or create delivery point with this group:
    #     set price_list_multiplier
    #     set transport
    #     set min transport


@receiver(post_delete, sender=Group)
def group_post_delete(sender, **kwargs):
    customer_post_delete(sender, **kwargs)
