# Copyright 2008 DeWitt Clinton
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Url patterns for the Ego Ego project."""

import django.conf.urls.defaults

from django.conf.urls.defaults import *

urlpatterns = django.conf.urls.defaults.patterns(
    '',
    (r'^/?$', 'views.HomeView'),
    (r'^user/$', 'views.UserRedirectView'),
    (r'^cref/$', 'views.CrefRedirectView'),
    (r'^osd/$', 'views.OsdRedirectView'),
    (r'^faq/$', 'views.FaqView'),
    (r'^friendfeed/(?P<nickname>[\w]+)/$', 'views.UserView'),
    (r'^friendfeed/(?P<nickname>[\w]+)/osd/$', 'views.OsdView'),
    (r'^friendfeed/(?P<nickname>[\w]+)/cref/$', 'views.CrefView'),
    (r'^friendfeed/(?P<nickname>[\w]+)/annotations/$', 'views.AnnotationView'),
    (r'^friendfeed/(?P<nickname>[\w]+)/annotations/(?P<start_index>[\d]+)/$', 'views.AnnotationView'),
    )
