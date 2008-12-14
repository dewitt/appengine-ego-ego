# Copyright 2008 DeWitt Clinton
#
# Portions Copyright Google, Inc., and reused under the Apache license from:
#
#   http://code.google.com/p/rietveld/source/browse/trunk/main.py
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

"""Set up initial paths, load Django and run the Django WSGIHandler."""

import logging
logging.debug('Beginning main.py')
import os
import re
import sys

os.environ['DJANGO_SETTINGS_MODULE'] = 'settings'

import google.appengine.ext.webapp.util

import django
import django.core
import django.core.handlers.wsgi
import django.core.mail
import django.db
import django.db.models
import django.db.models.signals
import django.dispatch.dispatcher
import django.middleware.common
import django.middleware.http
import django.template.loaders.filesystem

import simplejson

from xml.sax.saxutils import escape

import urls
import views

from django.conf import settings
settings._target = None

def log_exception(*args, **kwds):
  """Django signal handler to log an exception."""
  cls, err = sys.exc_info()[:2]
  logging.exception('Exception in request: %s: %s', cls.__name__, err)

django.dispatch.dispatcher.connect(
  log_exception, django.core.signals.got_request_exception)

django.dispatch.dispatcher.disconnect(
  django.db._rollback_on_exception, django.core.signals.got_request_exception)

def Main():
  """Main program."""
  logging.debug('Beginning Main()')
  application = django.core.handlers.wsgi.WSGIHandler()
  google.appengine.ext.webapp.util.run_wsgi_app(application)

if __name__ == '__main__':
  #import cProfile, pstats, StringIO
  #prof = cProfile.Profile()
  #prof = prof.runctx("Main()", globals(), locals())
  #stream = StringIO.StringIO()
  #stats = pstats.Stats(prof, stream=stream)
  #stats.sort_stats("time")  # Or cumulative
  #stats.print_stats(80)  # 80 = how many to print
  #logging.info("Profile data:\n%s", stream.getvalue())
  Main()
