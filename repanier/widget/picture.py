# -*- coding: utf-8

from django.core import urlresolvers
from django.core.files.storage import default_storage
from django.forms import widgets

from repanier.const import EMPTY_STRING
from repanier.picture.const import SIZE_M


class AjaxPictureWidget(widgets.TextInput):
    template_name = 'repanier/widgets/picture.html'

    def __init__(self, *args, **kwargs):
        self.upload_to = kwargs.pop('upload_to', 'pictures')
        self.size = kwargs.pop('size', SIZE_M)
        self.bootstrap = kwargs.pop('bootstrap', False)
        super(AjaxPictureWidget, self).__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super(AjaxPictureWidget, self).get_context(name, value, attrs)
        context['upload_url'] = urlresolvers.reverse(
            'ajax_picture', args=(self.upload_to, self.size)
        )
        if value:
            context['repanier_file_path'] = file_path = str(value)
            context['repanier_display_picture'] = "inline"
            context['repanier_display_upload'] = "none"
            context['repanier_file_url'] = default_storage.url(file_path)
        else:
            context['repanier_file_path'] = EMPTY_STRING
            context['repanier_display_picture'] = "none"
            context['repanier_display_upload'] = "inline"
            context['repanier_file_url'] = EMPTY_STRING

        context['repanier_height'] = context['repanier_width'] = self.size
        context['bootstrap'] = self.bootstrap
        return context
