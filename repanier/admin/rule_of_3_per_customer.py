# -*- coding: utf-8
from __future__ import unicode_literals

from django import forms
from django.contrib import admin
from django.db import transaction
from django.forms import BaseInlineFormSet
from django.utils import translation
from django.utils.translation import ugettext_lazy as _
from easy_select2 import Select2

from repanier.admin.fkey_choice_cache_mixin import ForeignKeyCacheMixin
from repanier.const import *
from repanier.fields.RepanierMoneyField import FormMoneyField, RepanierMoney
from repanier.models import Customer, Permanence, Producer, OfferItemSend, Purchase


class CustomerPurchaseSendInlineFormSet(BaseInlineFormSet):
    def clean(self):
        if any(self.errors):
            # Don't bother validating the formset unless each form is valid on its own
            return
        values = set()
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get('DELETE'):
                # This is not an empty form or a "to be deleted" form
                value = form.cleaned_data.get('offer_item', None)
                if value is not None:
                    if value in values:
                        raise forms.ValidationError(_('Duplicate offer_items are not allowed.'))
                    else:
                        values.add(value)


class CustomerPurchaseSendInlineForm(forms.ModelForm):
    previous_purchase_price = FormMoneyField(
        max_digits=8, decimal_places=2, required=False, initial=REPANIER_MONEY_ZERO)
    previous_offer_item = forms.ModelChoiceField(
        OfferItemSend.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        super(CustomerPurchaseSendInlineForm, self).__init__(*args, **kwargs)
        purchase = self.instance
        self.fields["previous_purchase_price"].initial = purchase.purchase_price
        self.fields["previous_offer_item"].initial = purchase.offer_item

    class Meta:
        widgets = {
            'offer_item': Select2(select2attrs={'width': '450px'})
        }


class CustomerPurchaseSendInline(ForeignKeyCacheMixin, admin.TabularInline):
    form = CustomerPurchaseSendInlineForm
    formset = CustomerPurchaseSendInlineFormSet
    model = Purchase
    fields = ['offer_item', 'quantity_invoiced',
              'get_html_producer_unit_price',
              'get_html_unit_deposit',
              'purchase_price', 'comment']
    readonly_fields = ['get_html_producer_unit_price', 'get_html_unit_deposit', ]
    extra = 0
    fk_name = 'customer_producer_invoice'
    parent_object = None

    def has_delete_permission(self, request, obj=None):
        return False

    def get_formset(self, request, obj=None, **kwargs):
        self.parent_object = obj
        return super(CustomerPurchaseSendInline, self).get_formset(request, obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "offer_item":
            # Important : allow is_active or not active offer_item, we are into the admin interface.
            kwargs["queryset"] = OfferItemSend.objects.filter(
                producer_id=self.parent_object.producer_id,
                permanence_id=self.parent_object.permanence_id,
                translations__language_code=translation.get_language()
            ).order_by("translations__preparation_sort_order", ).distinct()
        return super(CustomerPurchaseSendInline, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        qs = super(CustomerPurchaseSendInline, self).get_queryset(request)
        return qs.filter(
            is_box_content=False,
            offer_item__translations__language_code=translation.get_language(),
        ).order_by(
            "offer_item__translations__preparation_sort_order"
        ).distinct()


class CustomerSendForm(forms.ModelForm):
    offer_purchase_price = FormMoneyField(
        label=_("producer amount invoiced"), max_digits=8, decimal_places=2, required=False, initial=REPANIER_MONEY_ZERO)
    rule_of_3 = forms.BooleanField(
        label=_("apply rule of three"), required=False, initial=False)

    def __init__(self, *args, **kwargs):
        super(CustomerSendForm, self).__init__(*args, **kwargs)
        customer_producer_invoice = self.instance
        self.fields["offer_purchase_price"].initial = customer_producer_invoice.total_purchase_with_tax


class CustomerSendAdmin(admin.ModelAdmin):
    form = CustomerSendForm
    fields = (
        ('permanence', 'customer', 'producer',),
        ('offer_purchase_price', 'rule_of_3',)
    )
    list_per_page = 16
    list_max_show_all = 16
    inlines = [CustomerPurchaseSendInline]
    list_display = ('producer', 'customer', 'get_html_producer_price_purchased')
    list_display_links = ('customer',)
    search_fields = ('customer__short_basket_name',)
    ordering = ('customer',)

    def get_form(self, request, obj=None, **kwargs):
        form = super(CustomerSendAdmin, self).get_form(request, obj, **kwargs)

        permanence_field = form.base_fields["permanence"]
        customer_field = form.base_fields["customer"]
        producer_field = form.base_fields["producer"]

        permanence_field.widget.can_add_related = False
        customer_field.widget.can_add_related = False
        producer_field.widget.can_add_related = False
        permanence_field.widget.can_delete_related = False
        customer_field.widget.can_delete_related = False
        producer_field.widget.can_delete_related = False
        permanence_field.empty_label = None
        customer_field.empty_label = None
        producer_field.empty_label = None

        if obj is not None:
            permanence_field.queryset = Permanence.objects \
                .filter(id=obj.permanence_id)
            customer_field.queryset = Customer.objects \
                .filter(id=obj.customer_id)
            producer_field.queryset = Producer.objects \
                .filter(id=obj.producer_id)
        else:
            permanence_field.queryset = Permanence.objects.none()
            customer_field.queryset = Customer.objects.none()
            producer_field.queryset = Producer.objects.none()
        return form

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super(CustomerSendAdmin, self).get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        if not actions:
            try:
                self.list_display.remove('action_checkbox')
            except ValueError:
                pass
            except AttributeError:
                pass
        return actions

    def save_model(self, request, customer_producer_invoice, form, change):
        super(CustomerSendAdmin, self).save_model(
            request, customer_producer_invoice, form, change)

    @transaction.atomic
    def save_related(self, request, form, formsets, change):
        for formset in formsets:
            # option.py -> construct_change_message doesn't test the presence of those array not created at form initialisation...
            if not hasattr(formset, 'new_objects'): formset.new_objects = []
            if not hasattr(formset, 'changed_objects'): formset.changed_objects = []
            if not hasattr(formset, 'deleted_objects'): formset.deleted_objects = []
        customer_producer_invoice = form.instance
        customer = customer_producer_invoice.customer
        formset = formsets[0]
        for purchase_form in formset:
            purchase = purchase_form.instance
            previous_offer_item = purchase_form.fields['previous_offer_item'].initial
            if previous_offer_item is not None and previous_offer_item != purchase.offer_item:
                # Delete the purchase because the offer_item has changed
                purchase = Purchase.objects.filter(
                    customer_id=customer.id,
                    offer_item_id=previous_offer_item.id,
                    is_box_content=False
                ).order_by('?').first()
                if purchase is not None:
                    purchase.quantity_invoiced = DECIMAL_ZERO
                    purchase.save()
                    purchase.save_box()
        for purchase_form in formset:
            purchase_form_instance = purchase_form.instance
            offer_item = purchase_form_instance.offer_item
            if offer_item is None:
                purchase_form.repanier_is_valid = False
            else:
                purchase_form.repanier_is_valid = True
                # Reload purchase, because it has maybe be deleted
                purchase = Purchase.objects.filter(
                    customer_id=customer.id,
                    offer_item_id=offer_item.id,
                    is_box_content=False
                ).order_by('?').first()
                if purchase is None:
                    # Doesn't exists ? Create one
                    purchase = Purchase.objects.create(
                        permanence=offer_item.permanence,
                        permanence_date=offer_item.permanence.permanence_date,
                        offer_item=offer_item,
                        producer=offer_item.producer,
                        customer=customer,
                        quantity_ordered=DECIMAL_ZERO,
                        quantity_invoiced=DECIMAL_ZERO,
                        comment=purchase_form_instance.comment,
                        is_box_content=False,
                        status=PERMANENCE_SEND
                    )
                # And set the form's values
                purchase.quantity_invoiced = purchase_form_instance.quantity_invoiced
                purchase.purchase_price = purchase_form_instance.purchase_price
                purchase.comment = purchase_form_instance.comment
                # Set it as new form instance
                purchase_form.instance = purchase
                previous_purchase_price = purchase_form.fields['previous_purchase_price'].initial
                if purchase.purchase_price != previous_purchase_price:
                    if purchase.get_producer_unit_price() != DECIMAL_ZERO:
                        purchase.quantity_invoiced = (
                        purchase.purchase_price.amount / purchase.get_producer_unit_price()) \
                            .quantize(FOUR_DECIMALS)
                    else:
                        purchase.quantity_invoiced = DECIMAL_ZERO
        rule_of_3 = form.cleaned_data['rule_of_3']
        if rule_of_3:
            rule_of_3_target = form.cleaned_data['offer_purchase_price'].amount.quantize(TWO_DECIMALS)
            rule_of_3_source = DECIMAL_ZERO
            max_purchase_counter = 0
            for purchase_form in formset:
                if purchase_form.repanier_is_valid:
                    rule_of_3_source += purchase_form.instance.purchase_price.amount
                    max_purchase_counter += 1
            if rule_of_3_target is not None and rule_of_3_target != rule_of_3_source:
                if rule_of_3_source != DECIMAL_ZERO:
                    ratio = rule_of_3_target / rule_of_3_source
                else:
                    if rule_of_3_target == DECIMAL_ZERO:
                        ratio = DECIMAL_ZERO
                    else:
                        ratio = DECIMAL_ONE
                if ratio != DECIMAL_ONE:
                    adjusted_invoice = DECIMAL_ZERO
                    i = 0
                    for purchase_form in formset:
                        if purchase_form.repanier_is_valid:
                            i += 1
                            purchase = purchase_form.instance
                            if i == max_purchase_counter:
                                delta = (rule_of_3_target - adjusted_invoice).quantize(TWO_DECIMALS)
                                if purchase.get_producer_unit_price() != DECIMAL_ZERO:
                                    purchase.quantity_invoiced = (
                                        delta / purchase.get_producer_unit_price()).quantize(FOUR_DECIMALS)
                                else:
                                    purchase.quantity_invoiced = DECIMAL_ZERO
                            else:
                                purchase.quantity_invoiced = (purchase.quantity_invoiced * ratio).quantize(
                                    FOUR_DECIMALS)
                                adjusted_invoice += (
                                    purchase.quantity_invoiced * purchase.get_producer_unit_price()).quantize(
                                    TWO_DECIMALS)
                            purchase.save()
                            purchase.save_box()
        for purchase_form in formset:
            if purchase_form.has_changed() and purchase_form.repanier_is_valid:
                purchase_form.instance.save()
                purchase_form.instance.save_box()